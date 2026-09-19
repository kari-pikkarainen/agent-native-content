# Architecture

This document will describe the implemented system boundaries and data flow.
The authoritative target architecture is currently defined in
[`benchmark-spec.md`](benchmark-spec.md).

The benchmark will compare four independent arms while sharing retrieval
models, token accounting, and evaluation machinery wherever fairness requires
it. The canonical parsed document and normalized IR will remain separate from
derived retrieval indexes and immutable experiment outputs.

Architecture decisions should favor the smallest implementation capable of
testing the research hypothesis.
