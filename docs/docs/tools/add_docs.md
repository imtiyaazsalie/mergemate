# Add Docs

**Generates documentation for code components that are missing it — functions, classes, methods, and more.**

```
/add_docs
```

MergeMate scans the PR diff, identifies undocumented components, and posts inline documentation suggestions you can commit with one click.


## Language support

The tool detects the language and picks the right format automatically:

| Language | Doc style |
|---|---|
| Python | Docstrings (Sphinx, Google, NumPy) |
| Java | Javadoc |
| JavaScript / TypeScript | JSDoc |
| C++ | Doxygen |
| Other | Generic comment blocks |

## Configuration

(`[pr_add_docs]` section)

| Option | Default | Notes |
|---|---|---|
| `extra_instructions` | `""` | Additional guidance, e.g. "include usage examples for public methods." |
| `docs_style` | `"Sphinx"` | Python style: `"Sphinx"`, `"Google Style with Args, Returns, Attributes...etc"`, `"Numpy Style"`, `"PEP257"`, `"reStructuredText"`. |
| `file` | `""` | Target a specific file when multiple components share a name. |
| `class_name` | `""` | Target a specific class when methods share a name. |

Override inline:

```
/add_docs --pr_add_docs.docs_style="Numpy Style" --pr_add_docs.file="src/auth.py"
```

**Example config:**

```toml
[pr_add_docs]
docs_style = "Google Style with Args, Returns, Attributes...etc"
extra_instructions = "Focus on public interfaces and include type hints in examples."
```

## Tips

- **Run `/add_docs` before `/review`** — documented code reduces noise in review feedback.
- **Target a single file** with the `file` option when iterating on a specific module.
- **Pick the doc style your team already uses** so the output blends into the codebase.
