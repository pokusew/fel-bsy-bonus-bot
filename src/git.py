import os
import subprocess
from typing import Optional


class GithubGistClient:

    def __init__(self, gist: str, repo_dir: str, token: Optional[str] = None) -> None:
        self._gist = gist
        self._token = token
        self._repo_dir = repo_dir

    def get_https_url(self, with_token: bool = False) -> str:
        token = self._token + '@' if (with_token and self._token is not None) else ''
        return f"https://{token}gist.github.com/{self._gist}.git"

    def clone(self) -> None:
        full_url = self.get_https_url(with_token=True)
        subprocess.check_call(
            args=[
                'git',
                'clone',
                full_url,
                os.path.basename(self._repo_dir),
            ],
            cwd=os.path.dirname(self._repo_dir),
        )

    def pull(self) -> None:
        subprocess.check_call(
            args=[
                'git',
                'pull',
            ],
            cwd=self._repo_dir,
        )

    def push(self) -> None:
        subprocess.check_call(
            args=[
                'git',
                'push',
            ],
            cwd=self._repo_dir,
        )

    pass
