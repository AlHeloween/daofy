# Code Hosting: Git and Code Hosting Platform Tools

`code_hosting` is the unified entry point for all Git operations and code hosting platform APIs in Daofy. Agents must perform Git operations through this tool; calling `git` directly from the shell is prohibited.

## Supported Platforms

| Platform | `platform` | Authentication |
| --- | --- | --- |
| Gitea | `gitea` | `Authorization: token ...` |
| GitHub | `github` | `Authorization: Bearer ...` |
| GitLab | `gitlab` | `PRIVATE-TOKEN` |
| Gitee | `gitee` | `Authorization: Bearer ...` |
| GitCode | `gitcode` | `PRIVATE-TOKEN` |

Common API operation parameters:

- `base_url`: platform API root address, e.g. `https://code.qdac.cc:3000`, `https://api.github.com`.
- `token`: API access token. `create_token` is an exception and uses `username/password`.
- `repo`: repository name, in `owner/repo` format; GitLab/GitCode support `group/subgroup/project`.

## Action Quick Reference

| Group | Action | Description |
| --- | --- | --- |
| Git read-only | `git_status` | View repository status in compact format |
| Git read-only | `git_diff` | View working tree/staged changes |
| Git read-only | `git_show` | View a commit or object |
| Git read-only | `git_log` | View commit history |
| Git local write | `git_add` | Stage an explicit file list |
| Git local write | `git_commit` | Create a commit |
| Git remote sync | `git_fetch` | Fetch remote refs |
| Git remote sync | `git_pull` | Pull and merge/rebase |
| Git branches | `git_branch` | List, create, or delete branches |
| Git branches | `git_switch` | Switch to or create and switch to a branch |
| Git branches | `git_merge` | Merge branches |
| Git restore | `git_restore` | Restore explicit files; `files` is required |
| Git restore | `git_unstage` | Unstage explicit files; `files` is required |
| Git stash | `git_stash` | `push/list/pop/apply/drop/show` |
| Git tags | `git_tag` | List, create, or delete tags |
