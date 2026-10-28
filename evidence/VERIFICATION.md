# Verification of ResearchFlow 3.0.0

Prepared October 17, 2026. This file describes actual local execution, not an authenticated vendor certification.

## Results at a glance

| Executed check | Observed result |
|---|---|
| Final release regression suite, run in the staged installation | **56/56 passed**, 0 failures/errors/skips; 64.789 seconds |
| Synthetic updated-release regression suite | **56/56 passed**, 0 failures/errors/skips; 63.139 seconds |
| Installed offline failure → repair → review demo | Expected baseline **FAIL**, candidate **CHECKED**; fake model workers |
| Optional pytest adapter and output-producing example | **5/5 passed**; nonempty output and hash recorded |
| Fresh install and repeat install | Passed; existing settings preserved |
| Feedback, separate development copy, update and rollback | Passed; settings bytes, owner note and feedback preserved; previous version retained |
| Update with mismatched checksums / rollback while session lock held | Both correctly refused; active release unchanged |
| Executable source identity | Delivered code matches the source exercised by the final installed suite |
| macOS and live accounts | **NOT_RUN here**; run the supplied local/live checks on the Mac |

Evidence: [machine-readable summary](RESULTS.json), [full final suite log](final-tests.log), [installation steps](installation/results.json), [pytest observations](pytest/result.json).

These are repeated runs of the same 56 regressions, not 112 distinct tests. The five scientific example cases also appear in pipeline checks; do not add all repeated counts into a claimed coverage total.

## Current source

Final results and installation evidence are recorded alongside this file. The final package was built after the Cursor profile was corrected to the documented nested `editor.vimMode` JSON structure and a regression was added. Execution used Linux x86_64, Python 3.13.5, and Git 2.47.3. All model workers in local regression tests were fake executables.

## Reproduce the local checks

From the extracted ResearchFlow folder:

```bash
python3 -m compileall -q rf tests tools install.py researchflow.py
python3 -m unittest discover -s tests -v
python3 researchflow.py demo
```

The offline demo creates a NEW synthetic research repository. It preserves an unfinished source note, records a known failing normalization test, gets a fake Cursor method check, applies an explicit known repair, runs five example tests plus its output-producing example, and gets fake Codex review. Expected baseline is FAIL; candidate is CHECKED. This is not evidence that a real model implemented the repair.

## Tested boundaries

The suite covers raw-source and index preservation; original hooks not executed; unsafe configuration/filter/symlink refusal; persistent locks and active-session conflicts; bounded runtime/output and detached pipe holders; complete-packet secret screening including deleted lines and tasks; selected/alternate/unapproved Cursor models; strict Codex schema and missing output; zero/skipped/malformed/failed tests; missing artifacts; source/evidence/output staleness; blocked high review; bounded task attempts; absent pretend-human approval commands; full installed test fixtures; and checksummed releases including benign Finder metadata.

These checks establish these particular behaviors. They are not a proof of scientific validity, comprehensive privacy screening, or confinement against malicious same-user code.

## Installation lifecycle

The separate installer exercise uses a disposable home directory, installs a complete copy, invokes the stable launcher, repeats the install, runs the installed offline demo, saves feedback, makes an editable copy, installs a synthetic next version, refuses rollback during an active lock, refuses a checksum-mismatched update, and rolls back. Settings bytes, owner notes and feedback must survive; previous releases must remain. Detailed observations and commands are saved in installation/.

The same release self-tests run in the staged copy before activation, not only in the developer checkout. Final evidence files and a limitation note were added afterward; the controller, installer, release builder, regression tests, example code, lead prompt and task template were byte-compared with the tested source. Their hashes are in RESULTS.json. No behavior change was made after the installed test.

## Not run here

**macOS execution, real Claude/Cursor/Codex authentication, model quality, provider permission enforcement, subscription/quota handling, and the user's actual research projects were NOT_RUN.** Python 3.10 grammar compatibility is checked separately; runtime execution was Python 3.13.5 only. The optional pytest adapter was separately exercised on the five-case example; broad project-specific pytest plugin compatibility was not tested.

On the Mac, run `researchflow doctor`, then `researchflow demo --live` after permission to use accounts. The live smoke exercises one tiny Claude answer, one Cursor answer and one Codex review on synthetic data. It does not test arbitrary paper replication or fully autonomous live implementation.

Previous development results and the corrected initial fixture failure are kept under history/. Do not confuse them with final-release results.
