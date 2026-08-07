## Description
<!-- Clear summary of what this PR does and why -->


## Changes
<!-- List key changes -->
- 
- 

## Testing
<!-- How was this tested? -->
- [ ] Local tests pass (`pytest tests/ -m "not integration"`)
- [ ] THE_LAW checks pass (`scripts/law/check_structure.py`, `check_imports.py`)
- [ ] Pre-commit hooks pass
- [ ] Manual testing: <!-- describe what you tested -->

## THE_LAW Compliance
<!-- Check all that apply -->
- [ ] No directory exceeds 5 files + 5 subdirectories
- [ ] No .py file exceeds 500 lines
- [ ] All new files follow `d{depth}_{seq}_{word}_{word}.py` naming
- [ ] Imports respect depth DAG (only import from smaller depth)
- [ ] Required sections present in new files (Imports/Types/Constants/Entry/Core/Helpers/Errors)

## Related Issues
<!-- Link related issues, e.g. "Closes #123" -->


## Notes for Reviewers
<!-- Anything specific reviewers should focus on? -->
