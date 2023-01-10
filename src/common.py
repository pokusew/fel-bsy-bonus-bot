import os
import shutil
import subprocess
from typing import Optional, List, Any
import time
import json

IMAGES_LIBRARY = '4c7fe7e6d06b0b90ab4848b234209e95'
CONTROL_IMAGE = 'security.jpg'
UPDATE_INTERVAL = 30  # seconds
KEEP_ALIVE_TIMEOUT = 90 * 1000  # milliseconds

TMP_STATE_FILE = 'state.json'
TMP_ZIP_FILE = 'data.zip'


def is_image(file_name: str):
    return file_name.endswith('.png') or file_name.endswith('.jpg')


def now_ms() -> int:
    return time.time_ns() // 1000_000


def encode_data(image_file: str, data: Any, output_file: str):
    with open(TMP_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    subprocess.check_call(
        # needed otherwise zip output will be different every time because zip stores modification times
        args=['touch', '-t', '202212241800.00', TMP_STATE_FILE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        # -j junk paths (do not make directories)
        # -X Do not save extra file attributes (Extended Attributes on OS/2, uid/gid and file times on Unix).
        #    see https://stackoverflow.com/a/9714323
        args=['zip', '-jX', TMP_ZIP_FILE, TMP_STATE_FILE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        args=f"cat '{image_file}' '{TMP_ZIP_FILE}' > '{output_file}'",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.remove(TMP_STATE_FILE)
    os.remove(TMP_ZIP_FILE)


def decode_data(image_file_with_data: str) -> Any:
    # we are not checking exit code here because while unzipping the images with appended ZIP data
    # unzip produces warning [<file name>]:  xxx extra bytes at beginning or within zipfile
    # and exits a non-zero exit code
    # we could parse its stdout/stderr to find out if something was actually extracted
    subprocess.call(
        # -j junk paths (do not make directories)
        # -o overwrite files WITHOUT prompting
        args=['unzip', '-jo', image_file_with_data],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    data = None
    if os.path.isfile(TMP_STATE_FILE):
        with open(TMP_STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        os.remove(TMP_STATE_FILE)
    # note: if there were multiple files extracted from the image, they will remain in the workdir
    return data


class GithubGistClient:

    def __init__(self, gist: str, repo_dir: str, token: Optional[str] = None, author: Optional[str] = None) -> None:
        self._gist = gist
        self._token = token
        self._repo_dir = repo_dir
        self.author = author

    def get_repo_dir(self) -> str:
        return self._repo_dir

    def get_https_url(self, with_token: bool = False) -> str:
        token = self._token + '@' if (with_token and self._token is not None) else ''
        return f"https://{token}gist.github.com/{self._gist}.git"

    def verify(self) -> bool:
        if not os.path.isdir(self._repo_dir):
            return False
        p = subprocess.run(
            args=[
                'git',
                'remote',
                'get-url',
                'origin'
            ],
            encoding='utf-8',
            cwd=self._repo_dir,
            capture_output=True,
        )
        if p.returncode != 0:
            return False
        if p.stdout.rstrip() != self.get_https_url(with_token=True):
            return False
        return True

    def git_check_call(self, args: List[str]) -> None:
        subprocess.check_call(
            args=['git'] + args,
            cwd=self._repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def init(self, skip_reset: bool = False, skip_pull: bool = False) -> None:
        if self.verify():
            # git repo exists, just throw away all possible local changes and pull the latest remote
            if not skip_reset:
                self.git_check_call(['reset', '--hard', 'origin/main'])
            if not skip_pull:
                self.pull_changes()
            return
        # either the repo does not exist or it is invalid
        # first, make sure to delete whatever is in the place of the repo dir
        if os.path.isdir(self._repo_dir):
            shutil.rmtree(self._repo_dir)
        # it might be a file
        if os.path.exists(self._repo_dir):
            os.remove(self._repo_dir)
        # finally, we can clone the repo
        self.clone()

    def add(self, pathspecs: List[str]) -> bool:
        code = subprocess.call(
            args=['git', 'add'] + pathspecs,
            cwd=self._repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return code == 0

    def commit(self, message: str = 'Update') -> bool:
        args = ['git', 'commit', '-m', message]
        if self.author is not None:
            args += [f'--author={self.author}']
        code = subprocess.call(
            args=args,
            cwd=self._repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return code == 0

    def _pull(self) -> bool:
        code = subprocess.call(
            args=[
                'git',
                'pull',
                '--ff-only',
            ],
            cwd=self._repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return code == 0

    def _fetch(self) -> bool:
        code = subprocess.call(
            args=[
                'git',
                'fetch',
            ],
            cwd=self._repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return code == 0

    def _rebase(self) -> bool:
        code = subprocess.call(
            args=[
                'git',
                'rebase',
            ],
            cwd=self._repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if code != 0:
            subprocess.call(
                args=[
                    'git',
                    'rebase',
                    '--abort'
                ],
                cwd=self._repo_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return code == 0

    def _push(self) -> bool:
        code = subprocess.call(
            args=[
                'git',
                'push',
            ],
            cwd=self._repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return code == 0

    def pull_changes(self, max_retries: int = 2) -> None:
        # we do not anticipate any conflicts as we always pull changes
        # only when all local changes have been pushed first
        # the retries are here only to handle unexpected transient failures (e.g. network)
        for i in range(0, max_retries):
            if self._pull():
                return
        raise RuntimeError(f'pull_changes failed (max_retries={max_retries})')

    def push_changes(self, max_retries: int = 3) -> None:
        for i in range(0, max_retries):
            # try push
            if self._push():
                # successful, we are done
                print(f'push_changes succeeded attempt={i}')
                return
            # push failed probably, because of a conflict (we could parse the stderr of git push to be sure)
            # let's try to fetch the latest
            if not self._fetch():
                # execute error, retry the whole sequence
                continue
            if not self._rebase():
                # git rebase should normally never fail
                # if there is nothing to rebase it should also exit with 0 and "Current branch main is up to date.
                raise RuntimeError('git rebase failed')
            # continue with attempting to push
            continue
        raise RuntimeError(f'push_changes failed (max_retries={max_retries})')

    def commit_and_push_if_needed(self, max_retries: int = 3) -> None:
        if self.commit():
            self.push_changes(max_retries=max_retries)

    pass
