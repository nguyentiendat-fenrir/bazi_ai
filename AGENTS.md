
## Repository Hygiene & Minimal Artifacts

### 1. Core Principle

This is a production software engineering project, not a documentation-generation project.

Prioritize working, maintainable application code, meaningful automated tests, and essential technical documentation.

Avoid generating unnecessary files, redundant reports, duplicate scripts, or disposable artifacts.

### 2. File Creation Policy

Before creating a new file, determine whether an existing file or module can reasonably serve the same purpose.

Do not create separate files for trivial operations.

Do not create placeholder files, sample outputs, duplicate documentation, or intermediate JSON reports unless required by the task or acceptance criteria.

Do not impose artificial limits on the number of source files. Maintain appropriate module boundaries and separation of concerns.

### 3. Documentation Policy

Maintain the existing architecture specifications and API contracts as the source of truth.

Prefer updating existing documentation rather than creating new documents.

For each task, maintain one concise primary report:

`reports/tasks/TXXX.md`

The report should contain:
- Implemented functionality
- Files changed
- Tests executed and actual results
- Unresolved issues
- Acceptance status

Additional evidence files are permitted only when explicitly required by specifications, necessary for reproducibility or security, or genuinely useful for future maintenance.

Do not create multiple reports containing substantially identical information.

### 4. Temporary Files and Logs

Keep temporary outputs, local environments, caches, debug logs, and disposable artifacts outside tracked source directories.

Use ignored directories where appropriate, such as `.tools/`, `.cache/`, and `.artifacts/`.

Do not commit temporary output.

Never ignore or delete evidence explicitly required by acceptance criteria or audit specifications.

### 5. Tests and Scripts

Automated tests are first-class project assets.

Keep meaningful unit, integration, security, and regression tests.

Do not delete tests merely to reduce file count.

Prefer reusable utilities over multiple single-use scripts.

Remove genuinely disposable scripts only after confirming they are not required by the build, testing, recovery, or audit process.

### 6. Source Preservation

Never delete, overwrite, or silently modify:
- Original BaZi source code
- Original book files
- Required evidence
- Approved specifications
- Database migrations
- User-generated data

Do not change architecture, API contracts, or database schemas without following the project's existing change-control requirements.

### 7. Task Execution Discipline

Before starting a task:
1. Read its acceptance criteria.
2. Inspect relevant existing files.
3. Reuse existing implementations where possible.
4. Implement only the requested scope.

After implementation:
1. Run relevant tests.
2. Fix regressions.
3. Update the primary task report.
4. Update TASKS.md when appropriate.
5. Commit only the intended changes according to the project's Git rules.

Never mark a task complete without passing its required acceptance criteria.

### 8. Conflict Resolution

Preservation, security, testing, and explicit acceptance requirements take precedence over minimizing file count.

If a specification requires additional files or evidence, preserve them.

If documentation requirements conflict, report the conflict instead of silently deleting required artifacts.

### 9. Delivery Standard

Deliver working software, not an unnecessarily large collection of documentation.

Optimize for correctness, maintainability, traceability, and long-term extensibility.

## Repository Hygiene & Minimal Artifacts

### 1. Core Principle

This is a production software engineering project, not a documentation-generation project.

Prioritize working, maintainable application code, meaningful automated tests, and essential technical documentation.

Avoid generating unnecessary files, redundant reports, duplicate scripts, or disposable artifacts.

### 2. File Creation Policy

Before creating a new file, determine whether an existing file or module can reasonably serve the same purpose.

Do not create separate files for trivial operations.

Do not create placeholder files, sample outputs, duplicate documentation, or intermediate JSON reports unless required by the task or acceptance criteria.

Do not impose artificial limits on the number of source files. Maintain appropriate module boundaries and separation of concerns.

### 3. Documentation Policy

Maintain the existing architecture specifications and API contracts as the source of truth.

Prefer updating existing documentation rather than creating new documents.

For each task, maintain one concise primary report:

`reports/tasks/TXXX.md`

The report should contain:
- Implemented functionality
- Files changed
- Tests executed and actual results
- Unresolved issues
- Acceptance status

Additional evidence files are permitted only when explicitly required by specifications, necessary for reproducibility or security, or genuinely useful for future maintenance.

Do not create multiple reports containing substantially identical information.

### 4. Temporary Files and Logs

Keep temporary outputs, local environments, caches, debug logs, and disposable artifacts outside tracked source directories.

Use ignored directories where appropriate, such as `.tools/`, `.cache/`, and `.artifacts/`.

Do not commit temporary output.

Never ignore or delete evidence explicitly required by acceptance criteria or audit specifications.

### 5. Tests and Scripts

Automated tests are first-class project assets.

Keep meaningful unit, integration, security, and regression tests.

Do not delete tests merely to reduce file count.

Prefer reusable utilities over multiple single-use scripts.

Remove genuinely disposable scripts only after confirming they are not required by the build, testing, recovery, or audit process.

### 6. Source Preservation

Never delete, overwrite, or silently modify:
- Original BaZi source code
- Original book files
- Required evidence
- Approved specifications
- Database migrations
- User-generated data

Do not change architecture, API contracts, or database schemas without following the project's existing change-control requirements.

### 7. Task Execution Discipline

Before starting a task:
1. Read its acceptance criteria.
2. Inspect relevant existing files.
3. Reuse existing implementations where possible.
4. Implement only the requested scope.

After implementation:
1. Run relevant tests.
2. Fix regressions.
3. Update the primary task report.
4. Update TASKS.md when appropriate.
5. Commit only the intended changes according to the project's Git rules.

Never mark a task complete without passing its required acceptance criteria.

### 8. Conflict Resolution

Preservation, security, testing, and explicit acceptance requirements take precedence over minimizing file count.

If a specification requires additional files or evidence, preserve them.

If documentation requirements conflict, report the conflict instead of silently deleting required artifacts.

### 9. Delivery Standard

Deliver working software, not an unnecessarily large collection of documentation.

Optimize for correctness, maintainability, traceability, and long-term extensibility.
