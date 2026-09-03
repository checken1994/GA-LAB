# scp-ga ChatGPT Skill

Upload/install this folder (or its ZIP bundle) as one ChatGPT Skill named `scp-ga`.

It deliberately does not duplicate all 13 domain Skill files. Instead it requires ChatGPT to refresh the live GA-LAB `main` SHA, load SCP DNA, and then load the narrow domain Skill(s) from the same SHA. This prevents an installed copy from silently becoming a second authority.

The manifest records the build SHA and verification state. A package whose manifest is not `VERIFIED` must not be represented as evidence-verified.
