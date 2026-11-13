# Synthetic PPT acceptance gate

The standard-library gate checks a prepared synthetic state and replays ten
original negative cases. It checks the supplied font flag, local resource hashes,
layout flag, evidence references, privacy flag, recommendation wording, and
candidate receipt fields. Use only synthetic state and trusted local fixture paths.
The legacy font field is a Boolean input. The gate does not inspect fonts or PPT
files, render slides, or call Office, external providers or model gateways.

The two files are an extraction of the first-party synthetic acceptance checks.
To run the standalone controls with Python 3.11 or later from the repository root:

    python -I -B scripts/test_ppt_gate_checks.py

The source parsed and the ten fixtures matched the original synthetic fixture.
In the isolated execution attempt, temporary fixture creation was denied before
any of the 14 controls ran. Runtime behavior remains unverified.
