# Superseded installation attempt

An initial installation succeeded, but the evaluator then edited the source package while reusing its old manifest. The repeat-install attempt correctly stopped with a checksum mismatch. That was a test setup error, not a failed release upgrade. The entire final lifecycle was rerun against a frozen source copy, with 56 tests in each staged installation. See ../installation/results.json for the completed run. No test was bypassed.
