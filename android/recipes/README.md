# Private python-for-android recipes

This directory contains dependencies that need Android-specific build logic.
The `croc` recipe downloads the versioned source asset attached to the upstream
release, verifies its published SHA-256 checksum, builds against its vendored Go
modules, cross-compiles an ARM64 Android executable and packages it as
`libcroc.so`. The explicit release asset avoids depending on GitHub's generated
tag archives. Keeping recipes local prevents changes to the host's global
python-for-android installation.
