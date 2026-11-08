# Offline contract acceptance, v0.1.7

Three existing adapters are now portable public components: pinned offline CMS
schema validation, explicit-runtime AntV syntax inspection and shared slot budgets.
First-party Apache-2.0 is unchanged. Sveltia's MIT schema/license provenance is
retained; no upstream AntV JavaScript, CMS bundle, font or browser is distributed.

Host acceptance on Windows: Python3.12.11 directed suites33 tests,32 pass and
1 explicit symlink-privilege skip; Node22.17.1 directed suite14/14 pass. Total47,
46 pass/1 skip/0 failures. All synthetic data. The tests were authored by DeepSeek
from embedded source; the host independently ran and inspected them. Native tool
trace showed only the3 bridge-required bootstrap reads,4 output writes and1
bound result. Model-side tests were not authorized or run.

Separate real optional AntV0.2.11 parser checks cover8 invented template inputs
and shared registry coverage; canonical pinned CMS config validation also passes
(10 checks total). These checks execute syntax/structure, never a renderer/UI.

Fresh CPython3.13.5 independent offline venv, no system packages,15 pinned cached
dependencies plus public QRP0.1.2; dependency check0. Installed36 module origins,
17 CLI help entries,120 source/wheel/installed file-byte matches and the packaged
MIT notice pass. Installed CMS config and8 native optional-parser examples pass;
the installed hash-drift negative uses mocked decoded runtime metadata, with real
schema bytes. File-based hash/ref/dialect negatives are covered in source tests.

First failures retained separately: unsupported # comment in a host-authored
synthetic parser input, overly early host subprocess-denial hook import, Windows
stdlib temporary-directory write/cleanup permissions, and restricted-shell Node
test runner spawn EPERM. The sample comment/hook were corrected, the existing
scoped synthetic Windows temp adapter reused (no ACL edits or denied-path retry),
and the identical Node suite passed after one reviewed ordinary-user execution
outside the restricted shell. Tests/thresholds were not weakened; the denied
temporary directories were retained. No elevation or security-setting changes.

Not established: symlink enforcement on this Windows account, CMS bundle/SRI,
actual rendering, browser interaction, real evidence, author acceptance, account
access, audience outcomes or content publishing. No rough-cutP1 or browser-QA
candidate is included. This does not close the full multi-repository audit.
