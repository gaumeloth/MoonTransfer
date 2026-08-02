# Private python-for-android recipes

This directory contains dependencies that need Android-specific build logic.
The `croc` recipe downloads the pinned upstream source archive, verifies its
SHA-512 checksum, cross-compiles an ARM64 Android executable and packages it as
`libcroc.so`. Keeping recipes local prevents changes to the host's global
python-for-android installation.
