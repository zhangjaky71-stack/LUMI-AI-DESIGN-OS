# LUMI Video Generation

NODE-48 long-running video generation and timeline pipeline.

The service is dependency-free at runtime. Provider calls go through NODE-22 Model Gateway. Media composition is expressed as typed render specs and requires an injected sandbox executor; there is no shell fallback.
