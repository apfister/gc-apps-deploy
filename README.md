# gc-apps deploy action

Publishers consume this action through the moving major tag:

```yaml
- uses: apfister/gc-apps-platform/.github/actions/deploy@v1
  with:
    path: dist
```

The action requests a GitHub OIDC token for
`https://gcapps.esrigcazure.com/_deploy`, archives the contents of `path`, and
streams the Artifact to the receiver. The calling job must grant
`id-token: write`.

See [Publish an App](../../../docs/publishing.md) for registration, a complete
workflow, and failure guidance.

## Moving `v1`

Each release receives an immutable semantic tag such as `v1.0.0`. Move `v1`
only after that immutable tag passes the action integration test and a real
Deployment from the throwaway App. Move it deliberately:

```bash
git tag --annotate v1.0.0 --message "gc-apps deploy action v1.0.0"
git push origin refs/tags/v1.0.0
# Run the throwaway App against @v1.0.0 before moving the shared major tag.
git tag --force v1 'v1.0.0^{}'
git push --force origin refs/tags/v1
```

Breaking input or behavior changes require `v2`. If a release fails after the
move, point `v1` back to the previous verified immutable tag.