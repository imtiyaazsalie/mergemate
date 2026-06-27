"""PR Similar Issue tool — finds issues similar to the current one via vector search.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, List

import openai
from pydantic import BaseModel, ConfigDict, Field

from mergemate.algo import MAX_TOKENS
from mergemate.algo.token_handler import TokenHandler
from mergemate.algo.utils import get_max_tokens
from mergemate.config_loader import get_settings
from mergemate.git_providers import get_git_provider
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool

MODEL = "text-embedding-ada-002"


class IssueLevel(str, Enum):
    ISSUE = "issue"
    COMMENT = "comment"


class Metadata(BaseModel):
    repo: str
    username: str = Field(default="@mergemate")
    created_at: str = Field(default="01-01-1970 00:00:00.00000")
    level: IssueLevel = Field(default=IssueLevel.ISSUE)

    model_config = ConfigDict(use_enum_values=True)


class Record(BaseModel):
    id: str
    text: str
    metadata: Metadata


class Corpus(BaseModel):
    documents: List[Record] = Field(default=[])

    def append(self, r: Record):
        self.documents.append(r)


class PRSimilarIssue(BaseTool):
    """Finds similar issues via vector DB search and posts results.

    Pipeline:
        1. _prepare() — set up vector DB, get issue, create embedding
        2. _predict() — query vector DB for similar issues
        3. _publish() — format and post results as issue comment
    """

    @property
    def tool_name(self) -> str:
        return "similar_issue"

    # ------------------------------------------------------------------
    # Override _build_template_vars since we work with issues, not PRs
    # ------------------------------------------------------------------

    def _build_template_vars(self) -> dict[str, Any]:
        return {}

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Check support, initialise vector DB, get issue, create embedding."""
        self.supported = get_settings().config.git_provider == "github"
        if not self.supported:
            return

        self.max_issues_to_scan = get_settings().pr_similar_issue.max_issues_to_scan
        self._issue_provider = get_git_provider()()
        repo_name, issue_number = self._issue_provider._parse_issue_url(self.pr_url.split("=")[-1])
        self._issue_provider.repo = repo_name
        self._issue_provider.repo_obj = self._issue_provider.github_client.get_repo(repo_name)
        self.token_handler = TokenHandler()
        repo_obj = self._issue_provider.repo_obj
        self.repo_name_for_index = repo_obj.full_name.lower().replace("/", "-").replace("_/", "-")
        self.index_name = "mergemate-ai-mergemate-issues"

        self._init_vector_db()

        get_logger().info("Getting issue...")
        self.original_issue_number = issue_number
        self.issue_main = self._issue_provider.repo_obj.get_issue(issue_number)
        issue_str, _comments, _number = self._process_issue(self.issue_main)
        openai.api_key = get_settings().openai.key
        get_logger().info("Done")

        get_logger().info("Creating embedding...")
        res = openai.Embedding.create(input=[issue_str], engine=MODEL)
        self.embeds = [record["embedding"] for record in res["data"]]
        get_logger().info("Done")

    async def _predict(self) -> dict[str, Any]:
        """Query vector DB and return similar issues."""
        if not self.supported:
            return {"supported": False}

        get_logger().info("Querying...")
        vectordb = get_settings().pr_similar_issue.vectordb

        relevant_issues_number_list = []
        relevant_comment_number_list = []
        score_list = []

        if vectordb == "pinecone":
            self._query_pinecone(
                self.original_issue_number,
                relevant_issues_number_list,
                relevant_comment_number_list,
                score_list,
            )
        elif vectordb == "lancedb":
            self._query_lancedb(
                self.original_issue_number,
                relevant_issues_number_list,
                relevant_comment_number_list,
                score_list,
            )
        elif vectordb == "qdrant":
            self._query_qdrant(
                self.original_issue_number,
                relevant_issues_number_list,
                relevant_comment_number_list,
                score_list,
            )

        get_logger().info("Done")
        return {
            "supported": True,
            "relevant_issues": relevant_issues_number_list,
            "relevant_comments": relevant_comment_number_list,
            "scores": score_list,
        }

    async def _publish(self, result: dict[str, Any]) -> None:
        """Format and post similar issues as a comment."""
        if not result["supported"]:
            message = "The /similar_issue tool is currently supported only for GitHub."
            if self.config.publish_output:
                try:
                    from mergemate.git_providers import get_git_provider_with_context

                    provider = get_git_provider_with_context(self.pr_url)
                    provider.publish_comment(message)
                except Exception as e:
                    get_logger().warning(
                        "Failed to publish /similar_issue unsupported message",
                        artifact={"error": str(e)},
                    )
            return

        get_logger().info("Publishing response...")
        similar_issues_str = "### Similar Issues\n___\n\n"

        for i, issue_number_similar in enumerate(result["relevant_issues"]):
            issue = self._issue_provider.repo_obj.get_issue(issue_number_similar)
            title = issue.title
            url = issue.html_url
            if result["relevant_comments"][i] != -1:
                url = list(issue.get_comments())[result["relevant_comments"][i]].html_url
            similar_issues_str += f"{i + 1}. **[{title}]({url})** (score={result['scores'][i]})\n\n"

        if self.config.publish_output:
            self.issue_main.create_comment(similar_issues_str)
        get_logger().info(similar_issues_str)
        get_logger().info("Done")

    # ------------------------------------------------------------------
    # Vector DB query helpers
    # ------------------------------------------------------------------

    def _query_pinecone(self, original_issue_number, relevant_issues, relevant_comments, scores):
        import pinecone

        pinecone_index = pinecone.Index(index_name=self.index_name)
        res = pinecone_index.query(
            self.embeds[0],
            top_k=5,
            filter={"repo": self.repo_name_for_index},
            include_metadata=True,
        ).to_dict()
        for r in res["matches"]:
            if "example_issue_" in r["id"]:
                continue
            try:
                issue_number = int(r["id"].split(".")[0].split("_")[-1])
            except Exception:
                get_logger().debug(f"Failed to parse issue number from {r['id']}")
                continue
            if original_issue_number == issue_number:
                continue
            if issue_number not in relevant_issues:
                relevant_issues.append(issue_number)
            if "comment" in r["id"]:
                relevant_comments.append(int(r["id"].split(".")[1].split("_")[-1]))
            else:
                relevant_comments.append(-1)
            scores.append(str("{:.2f}".format(r["score"])))

    def _query_lancedb(self, original_issue_number, relevant_issues, relevant_comments, scores):
        res = (
            self.table.search(self.embeds[0])
            .where(f"metadata.repo='{self.repo_name_for_index}'", prefilter=True)
            .to_list()
        )
        for r in res:
            if "example_issue_" in r["id"]:
                continue
            try:
                issue_number = int(r["id"].split(".")[0].split("_")[-1])
            except Exception:
                get_logger().debug(f"Failed to parse issue number from {r['id']}")
                continue
            if original_issue_number == issue_number:
                continue
            if issue_number not in relevant_issues:
                relevant_issues.append(issue_number)
            if "comment" in r["id"]:
                relevant_comments.append(int(r["id"].split(".")[1].split("_")[-1]))
            else:
                relevant_comments.append(-1)
            scores.append(str("{:.2f}".format(1 - r["_distance"])))

    def _query_qdrant(self, original_issue_number, relevant_issues, relevant_comments, scores):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        res = self.qdrant.search(
            collection_name=self.index_name,
            query_vector=self.embeds[0],
            limit=5,
            query_filter=Filter(
                must=[FieldCondition(key="metadata.repo", match=MatchValue(value=self.repo_name_for_index))]
            ),
            with_payload=True,
        )
        for r in res:
            rid = r.payload.get("id", "")
            if "example_issue_" in rid:
                continue
            try:
                issue_number = int(rid.split(".")[0].split("_")[-1])
            except Exception:
                get_logger().debug(f"Failed to parse issue number from {rid}")
                continue
            if original_issue_number == issue_number:
                continue
            if issue_number not in relevant_issues:
                relevant_issues.append(issue_number)
            if "comment" in rid:
                relevant_comments.append(int(rid.split(".")[1].split("_")[-1]))
            else:
                relevant_comments.append(-1)
            scores.append(str("{:.2f}".format(r.score)))

    # ------------------------------------------------------------------
    # Vector DB initialisation
    # ------------------------------------------------------------------

    def _init_vector_db(self) -> None:
        vectordb = get_settings().pr_similar_issue.vectordb
        repo_obj = self._issue_provider.repo_obj

        if vectordb == "pinecone":
            self._init_pinecone(repo_obj)
        elif vectordb == "lancedb":
            self._init_lancedb(repo_obj)
        elif vectordb == "qdrant":
            self._init_qdrant(repo_obj)

    def _init_pinecone(self, repo_obj) -> None:
        try:
            import pandas as pd
            import pinecone
        except Exception:
            raise Exception("Please install 'pinecone' and 'pinecone_datasets' to use pinecone as vectordb")

        try:
            api_key = get_settings().pinecone.api_key
            environment = get_settings().pinecone.environment
        except Exception:
            if not self.config.cli_mode:
                repo_name, original_issue_number = self._issue_provider._parse_issue_url(self.pr_url.split("=")[-1])
                issue_main = self._issue_provider.repo_obj.get_issue(original_issue_number)
                issue_main.create_comment("Please set pinecone api key and environment in secrets file")
            raise Exception("Please set pinecone api key and environment in secrets file")

        run_from_scratch = False
        upsert = True
        pinecone.init(api_key=api_key, environment=environment)
        if self.index_name not in pinecone.list_indexes():
            run_from_scratch = True
            upsert = False
        else:
            if get_settings().pr_similar_issue.force_update_dataset:
                upsert = True
            else:
                pinecone_index = pinecone.Index(index_name=self.index_name)
                res = pinecone_index.fetch([f"example_issue_{self.repo_name_for_index}"]).to_dict()
                if res["vectors"]:
                    upsert = False

        if run_from_scratch or upsert:
            get_logger().info("Indexing the entire repo...")
            get_logger().info("Getting issues...")
            issues = list(repo_obj.get_issues(state="all"))
            get_logger().info("Done")
            self._update_index_with_issues(issues, self.repo_name_for_index, upsert=upsert)
        else:
            pinecone_index = pinecone.Index(index_name=self.index_name)
            issues_to_update = []
            issues_paginated_list = repo_obj.get_issues(state="all")
            counter = 1
            for issue in issues_paginated_list:
                if issue.pull_request:
                    continue
                _issue_str, _comments, number = self._process_issue(issue)
                issue_key = f"issue_{number}"
                issue_id = issue_key + "." + "issue"
                res = pinecone_index.fetch([issue_id]).to_dict()
                is_new_issue = True
                for vector in res["vectors"].values():
                    if vector["metadata"]["repo"] == self.repo_name_for_index:
                        is_new_issue = False
                        break
                if is_new_issue:
                    counter += 1
                    issues_to_update.append(issue)
                else:
                    break
            if issues_to_update:
                get_logger().info(f"Updating index with {counter} new issues...")
                self._update_index_with_issues(issues_to_update, self.repo_name_for_index, upsert=True)
            else:
                get_logger().info("No new issues to update")

    def _init_lancedb(self, repo_obj) -> None:
        try:
            import lancedb
        except Exception:
            raise Exception("Please install lancedb to use lancedb as vectordb")

        self.db = lancedb.connect(get_settings().lancedb.uri)
        self.table = None

        ingest = True
        if self.index_name not in self.db.table_names():
            ingest = False
        else:
            if get_settings().pr_similar_issue.force_update_dataset:
                ingest = True
            else:
                self.table = self.db[self.index_name]
                res = (
                    self.table.search()
                    .limit(len(self.table))
                    .where(f"id='example_issue_{self.repo_name_for_index}'")
                    .to_list()
                )
                get_logger().info("result: ", res)
                if res[0].get("vector"):
                    ingest = False

        if ingest:
            get_logger().info("Indexing the entire repo...")
            get_logger().info("Getting issues...")
            issues = list(repo_obj.get_issues(state="all"))
            get_logger().info("Done")
            self._update_table_with_issues(issues, self.repo_name_for_index, ingest=ingest)
        else:
            issues_to_update = []
            issues_paginated_list = repo_obj.get_issues(state="all")
            counter = 1
            for issue in issues_paginated_list:
                if issue.pull_request:
                    continue
                _issue_str, _comments, number = self._process_issue(issue)
                issue_key = f"issue_{number}"
                issue_id = issue_key + "." + "issue"
                res = self.table.search().limit(len(self.table)).where(f"id='{issue_id}'").to_list()
                is_new_issue = True
                for r in res:
                    if r["metadata"]["repo"] == self.repo_name_for_index:
                        is_new_issue = False
                        break
                if is_new_issue:
                    counter += 1
                    issues_to_update.append(issue)
                else:
                    break
            if issues_to_update:
                get_logger().info(f"Updating index with {counter} new issues...")
                self._update_table_with_issues(issues_to_update, self.repo_name_for_index, ingest=True)
            else:
                get_logger().info("No new issues to update")

    def _init_qdrant(self, repo_obj) -> None:
        try:
            import qdrant_client
            from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams
        except Exception:
            raise Exception("Please install qdrant-client to use qdrant as vectordb")

        api_key = None
        url = None
        try:
            api_key = get_settings().qdrant.api_key
            url = get_settings().qdrant.url
        except Exception:
            if not self.config.cli_mode:
                repo_name, original_issue_number = self._issue_provider._parse_issue_url(self.pr_url.split("=")[-1])
                issue_main = self._issue_provider.repo_obj.get_issue(original_issue_number)
                issue_main.create_comment("Please set qdrant url and api key in secrets file")
            raise Exception("Please set qdrant url and api key in secrets file")

        self.qdrant = qdrant_client.QdrantClient(url=url, api_key=api_key)

        run_from_scratch = False
        ingest = True

        if not self.qdrant.collection_exists(collection_name=self.index_name):
            run_from_scratch = True
            ingest = False
            self.qdrant.create_collection(
                collection_name=self.index_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )
        else:
            if get_settings().pr_similar_issue.force_update_dataset:
                ingest = True
            else:
                response = self.qdrant.count(
                    collection_name=self.index_name,
                    count_filter=Filter(
                        must=[
                            FieldCondition(key="metadata.repo", match=MatchValue(value=self.repo_name_for_index)),
                            FieldCondition(
                                key="id", match=MatchValue(value=f"example_issue_{self.repo_name_for_index}")
                            ),
                        ]
                    ),
                )
                ingest = True if response.count == 0 else False

        if run_from_scratch or ingest:
            get_logger().info("Indexing the entire repo...")
            get_logger().info("Getting issues...")
            issues = list(repo_obj.get_issues(state="all"))
            get_logger().info("Done")
            self._update_qdrant_with_issues(issues, self.repo_name_for_index, ingest=ingest)
        else:
            issues_to_update = []
            issues_paginated_list = repo_obj.get_issues(state="all")
            counter = 1
            for issue in issues_paginated_list:
                if issue.pull_request:
                    continue
                _issue_str, _comments, number = self._process_issue(issue)
                issue_key = f"issue_{number}"
                point_id = issue_key + "." + "issue"
                response = self.qdrant.count(
                    collection_name=self.index_name,
                    count_filter=Filter(
                        must=[
                            FieldCondition(key="id", match=MatchValue(value=point_id)),
                            FieldCondition(key="metadata.repo", match=MatchValue(value=self.repo_name_for_index)),
                        ]
                    ),
                )
                if response.count == 0:
                    counter += 1
                    issues_to_update.append(issue)
                else:
                    break
            if issues_to_update:
                get_logger().info(f"Updating index with {counter} new issues...")
                self._update_qdrant_with_issues(issues_to_update, self.repo_name_for_index, ingest=True)
            else:
                get_logger().info("No new issues to update")

    # ------------------------------------------------------------------
    # Issue processing & index building
    # ------------------------------------------------------------------

    def _process_issue(self, issue):
        header = issue.title
        body = issue.body
        number = issue.number
        if get_settings().pr_similar_issue.skip_comments:
            comments = []
        else:
            comments = list(issue.get_comments())
        issue_str = f'Issue Header: "{header}"\n\nIssue Body:\n{body}'
        return issue_str, comments, number

    def _update_index_with_issues(self, issues_list, repo_name_for_index, upsert=False):
        import pandas as pd
        from pinecone_datasets import Dataset, DatasetMetadata

        get_logger().info("Processing issues...")
        corpus = Corpus()
        example_issue_record = Record(
            id=f"example_issue_{repo_name_for_index}",
            text="example_issue",
            metadata=Metadata(repo=repo_name_for_index),
        )
        corpus.append(example_issue_record)

        counter = 0
        for issue in issues_list:
            if issue.pull_request:
                continue
            counter += 1
            if counter % 100 == 0:
                get_logger().info(f"Scanned {counter} issues")
            if counter >= self.max_issues_to_scan:
                get_logger().info(f"Scanned {self.max_issues_to_scan} issues, stopping")
                break
            issue_str, comments, number = self._process_issue(issue)
            issue_key = f"issue_{number}"
            username = issue.user.login
            created_at = str(issue.created_at)
            if len(issue_str) < 8000 or self.token_handler.count_tokens(issue_str) < get_max_tokens(MODEL):
                issue_record = Record(
                    id=issue_key + "." + "issue",
                    text=issue_str,
                    metadata=Metadata(
                        repo=repo_name_for_index,
                        username=username,
                        created_at=created_at,
                        level=IssueLevel.ISSUE,
                    ),
                )
                corpus.append(issue_record)
                if comments:
                    for j, comment in enumerate(comments):
                        comment_body = comment.body
                        num_words_comment = len(comment_body.split())
                        if num_words_comment < 10 or not isinstance(comment_body, str):
                            continue
                        if (
                            len(comment_body) < 8000
                            or self.token_handler.count_tokens(comment_body) < MAX_TOKENS[MODEL]
                        ):
                            comment_record = Record(
                                id=issue_key + ".comment_" + str(j + 1),
                                text=comment_body,
                                metadata=Metadata(
                                    repo=repo_name_for_index,
                                    username=username,
                                    created_at=created_at,
                                    level=IssueLevel.COMMENT,
                                ),
                            )
                            corpus.append(comment_record)
        df = pd.DataFrame(corpus.model_dump()["documents"])
        get_logger().info("Done")

        get_logger().info("Embedding...")
        openai.api_key = get_settings().openai.key
        list_to_encode = list(df["text"].values)
        try:
            res = openai.Embedding.create(input=list_to_encode, engine=MODEL)
            embeds = [record["embedding"] for record in res["data"]]
        except Exception:
            embeds = []
            get_logger().error("Failed to embed entire list, embedding one by one...")
            for _i, text in enumerate(list_to_encode):
                try:
                    res = openai.Embedding.create(input=[text], engine=MODEL)
                    embeds.append(res["data"][0]["embedding"])
                except Exception:
                    embeds.append([0] * 1536)
        df["values"] = embeds
        meta = DatasetMetadata.empty()
        meta.dense_model.dimension = len(embeds[0])
        ds = Dataset.from_pandas(df, meta)
        get_logger().info("Done")

        api_key = get_settings().pinecone.api_key
        environment = get_settings().pinecone.environment
        if not upsert:
            get_logger().info("Creating index from scratch...")
            ds.to_pinecone_index(self.index_name, api_key=api_key, environment=environment)
            time.sleep(15)
        else:
            get_logger().info("Upserting index...")
            namespace = ""
            batch_size: int = 100
            concurrency: int = 10
            import pinecone

            pinecone.init(api_key=api_key, environment=environment)
            ds._upsert_to_index(self.index_name, namespace, batch_size, concurrency)
            time.sleep(5)
        get_logger().info("Done")

    def _update_table_with_issues(self, issues_list, repo_name_for_index, ingest=False):
        import pandas as pd

        get_logger().info("Processing issues...")
        corpus = Corpus()
        example_issue_record = Record(
            id=f"example_issue_{repo_name_for_index}",
            text="example_issue",
            metadata=Metadata(repo=repo_name_for_index),
        )
        corpus.append(example_issue_record)

        counter = 0
        for issue in issues_list:
            if issue.pull_request:
                continue
            counter += 1
            if counter % 100 == 0:
                get_logger().info(f"Scanned {counter} issues")
            if counter >= self.max_issues_to_scan:
                get_logger().info(f"Scanned {self.max_issues_to_scan} issues, stopping")
                break
            issue_str, comments, number = self._process_issue(issue)
            issue_key = f"issue_{number}"
            username = issue.user.login
            created_at = str(issue.created_at)
            if len(issue_str) < 8000 or self.token_handler.count_tokens(issue_str) < get_max_tokens(MODEL):
                issue_record = Record(
                    id=issue_key + "." + "issue",
                    text=issue_str,
                    metadata=Metadata(
                        repo=repo_name_for_index,
                        username=username,
                        created_at=created_at,
                        level=IssueLevel.ISSUE,
                    ),
                )
                corpus.append(issue_record)
                if comments:
                    for j, comment in enumerate(comments):
                        comment_body = comment.body
                        num_words_comment = len(comment_body.split())
                        if num_words_comment < 10 or not isinstance(comment_body, str):
                            continue
                        if (
                            len(comment_body) < 8000
                            or self.token_handler.count_tokens(comment_body) < MAX_TOKENS[MODEL]
                        ):
                            comment_record = Record(
                                id=issue_key + ".comment_" + str(j + 1),
                                text=comment_body,
                                metadata=Metadata(
                                    repo=repo_name_for_index,
                                    username=username,
                                    created_at=created_at,
                                    level=IssueLevel.COMMENT,
                                ),
                            )
                            corpus.append(comment_record)
        df = pd.DataFrame(corpus.model_dump()["documents"])
        get_logger().info("Done")

        get_logger().info("Embedding...")
        openai.api_key = get_settings().openai.key
        list_to_encode = list(df["text"].values)
        try:
            res = openai.Embedding.create(input=list_to_encode, engine=MODEL)
            embeds = [record["embedding"] for record in res["data"]]
        except Exception:
            embeds = []
            get_logger().error("Failed to embed entire list, embedding one by one...")
            for _i, text in enumerate(list_to_encode):
                try:
                    res = openai.Embedding.create(input=[text], engine=MODEL)
                    embeds.append(res["data"][0]["embedding"])
                except Exception:
                    embeds.append([0] * 1536)
        df["vector"] = embeds
        get_logger().info("Done")

        if not ingest:
            get_logger().info("Creating table from scratch...")
            self.table = self.db.create_table(self.index_name, data=df, mode="overwrite")
            time.sleep(15)
        else:
            get_logger().info("Ingesting in Table...")
            if self.index_name not in self.db.table_names():
                self.table.add(df)
            else:
                get_logger().info(f"Table {self.index_name} doesn't exists!")
            time.sleep(5)
        get_logger().info("Done")

    def _update_qdrant_with_issues(self, issues_list, repo_name_for_index, ingest=False):
        try:
            import uuid

            import pandas as pd
            from qdrant_client.models import PointStruct
        except Exception:
            raise

        get_logger().info("Processing issues...")
        corpus = Corpus()
        example_issue_record = Record(
            id=f"example_issue_{repo_name_for_index}",
            text="example_issue",
            metadata=Metadata(repo=repo_name_for_index),
        )
        corpus.append(example_issue_record)

        counter = 0
        for issue in issues_list:
            if issue.pull_request:
                continue
            counter += 1
            if counter % 100 == 0:
                get_logger().info(f"Scanned {counter} issues")
            if counter >= self.max_issues_to_scan:
                get_logger().info(f"Scanned {self.max_issues_to_scan} issues, stopping")
                break
            issue_str, comments, number = self._process_issue(issue)
            issue_key = f"issue_{number}"
            username = issue.user.login
            created_at = str(issue.created_at)
            if len(issue_str) < 8000 or self.token_handler.count_tokens(issue_str) < get_max_tokens(MODEL):
                issue_record = Record(
                    id=issue_key + "." + "issue",
                    text=issue_str,
                    metadata=Metadata(
                        repo=repo_name_for_index,
                        username=username,
                        created_at=created_at,
                        level=IssueLevel.ISSUE,
                    ),
                )
                corpus.append(issue_record)
                if comments:
                    for j, comment in enumerate(comments):
                        comment_body = comment.body
                        num_words_comment = len(comment_body.split())
                        if num_words_comment < 10 or not isinstance(comment_body, str):
                            continue
                        if (
                            len(comment_body) < 8000
                            or self.token_handler.count_tokens(comment_body) < MAX_TOKENS[MODEL]
                        ):
                            comment_record = Record(
                                id=issue_key + ".comment_" + str(j + 1),
                                text=comment_body,
                                metadata=Metadata(
                                    repo=repo_name_for_index,
                                    username=username,
                                    created_at=created_at,
                                    level=IssueLevel.COMMENT,
                                ),
                            )
                            corpus.append(comment_record)

        df = pd.DataFrame(corpus.model_dump()["documents"])
        get_logger().info("Done")

        get_logger().info("Embedding...")
        openai.api_key = get_settings().openai.key
        list_to_encode = list(df["text"].values)
        try:
            res = openai.Embedding.create(input=list_to_encode, engine=MODEL)
            embeds = [record["embedding"] for record in res["data"]]
        except Exception:
            embeds = []
            get_logger().error("Failed to embed entire list, embedding one by one...")
            for _i, text in enumerate(list_to_encode):
                try:
                    res = openai.Embedding.create(input=[text], engine=MODEL)
                    embeds.append(res["data"][0]["embedding"])
                except Exception:
                    embeds.append([0] * 1536)
        df["vector"] = embeds
        get_logger().info("Done")

        get_logger().info("Upserting into Qdrant...")
        points = []
        for row in df.to_dict(orient="records"):
            points.append(
                PointStruct(
                    id=uuid.uuid5(uuid.NAMESPACE_DNS, row["id"]).hex,
                    vector=row["vector"],
                    payload={"id": row["id"], "text": row["text"], "metadata": row["metadata"]},
                )
            )
        self.qdrant.upsert(collection_name=self.index_name, points=points)
        get_logger().info("Done")


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_similar_issue_class() -> type:
    """Return the PRSimilarIssue class for the tool registry factory."""
    return PRSimilarIssue
