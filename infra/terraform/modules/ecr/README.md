# `ecr` module

One private repository per deployable image: `<name_prefix>/api` (also runs the worker, `migrate`, `seed-demo` and `create-owner`) and `<name_prefix>/web`. Tags are immutable so a deployed tag always means the same bytes, images are scanned on push, untagged layers expire after 7 days and only the newest `keep_images` tagged images are kept.

Not applied in `local-floci`: Compose builds the images locally (`gpuwatch-api:local`, `gpuwatch-web:local`).

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Repositories are named `<name_prefix>/<image>`. | `string` | required |
| `repositories` | Images to create repositories for. | `list(string)` | `["api", "web"]` |
| `kms_key_arn` | CMK for repository encryption. Null uses AES256. | `string` | `null` |
| `keep_images` | Tagged images kept per repository. | `number` | `30` |
| `force_delete` | Allow destroying a repository that still holds images. | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `repository_urls` | Map of image name to repository URL. |
| `repository_arns` | Map of image name to repository ARN. |
