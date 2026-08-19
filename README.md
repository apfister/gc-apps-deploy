# GC Apps deploy action

Publish a finished static or service Artifact to GC Apps using GitHub's short-lived OIDC
identity. The action creates no deployment secret and runs no App build code.

## Usage

The calling job must run on a GitHub-hosted runner and grant `id-token: write`:

```yaml
permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - run: npm ci && npm run build
      - uses: apfister/gc-apps-deploy@v1
        with:
          path: dist
```

The `path` input defaults to `dist`. A static Artifact must contain regular root
`index.html`; a service Artifact must contain regular root `gcapps.json`. Artifacts
may contain only regular files and directories. The platform validates the selected
App Type and complete Artifact contract.

The action requests an OIDC token for
`https://gcapps.esrigcazure.com/_deploy`, archives the Artifact, and streams it
to the platform. The repository must be registered with a GC Apps Operator
before its first Deployment.

## Releases

Semantic tags such as `v1.0.0` are immutable. The moving `v1` tag changes only
after the immutable tag passes the action integration test and a real canary
Deployment. Breaking input or behavior changes require a new major version.

## Security

Do not print the GitHub OIDC token or add a long-lived platform credential. The
action masks the token before uploading the Artifact. Report vulnerabilities
privately to the repository owner rather than opening a public issue with
credential or platform details.

## License

MIT