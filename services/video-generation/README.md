# LUMI Video Generation — NODE-48

Provider-neutral long-running video generation and composition control plane.

The service owns storyboard compilation, shot lifecycle, async provider coordination, validation, typed render specifications and provenance. It does not own provider credentials, monetary settlement, binary asset storage, or Artifact Engine truth.

Production composition binds FFmpeg only through a sandbox executor. Provider jobs must enter `PENDING` after submit; polling/webhooks resume work outside the Agent/LangGraph request path.
