import os
import shutil
import subprocess
from abc import ABC
from typing import Optional, List, Any
import time
from datetime import datetime
import json

from terminal import gray, rst, cyan, magenta

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


def format_timestamp(millis: int) -> str:
    return datetime.fromtimestamp(millis / 1000).strftime("%m/%d/%Y at %H:%M:%S")


def encode_data(image_file: str, data: Any, output_file: str, additional_files_to_zip: Optional[List[str]] = None):
    with open(TMP_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    subprocess.check_call(
        # needed otherwise zip output will be different every time because zip stores modification times
        args=['touch', '-t', '202212241800.00', TMP_STATE_FILE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # -j junk paths (do not make directories)
    # -X Do not save extra file attributes (Extended Attributes on OS/2, uid/gid and file times on Unix).
    #    see https://stackoverflow.com/a/9714323
    zip_args = ['zip', '-jX', TMP_ZIP_FILE, TMP_STATE_FILE]
    if isinstance(additional_files_to_zip, list):
        zip_args += additional_files_to_zip
    subprocess.check_call(
        args=zip_args,
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


def decode_data(image_file_with_data: str, out_dir: Optional[str] = None) -> Any:
    # we are not checking exit code here because while unzipping the images with appended ZIP data
    # unzip produces warning [<file name>]:  xxx extra bytes at beginning or within zipfile
    # and exits a non-zero exit code
    # we could parse its stdout/stderr to find out if something was actually extracted
    # -j junk paths (do not make directories)
    # -o overwrite files WITHOUT prompting
    args = ['unzip', '-jo', image_file_with_data]
    if out_dir is not None:
        # -d exdir An optional directory to which to extract files
        args += ['-d', out_dir]
    subprocess.call(
        args=args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    data = None
    tmp_state_file = os.path.join(out_dir, TMP_STATE_FILE) if out_dir is not None else TMP_STATE_FILE
    if os.path.isfile(tmp_state_file):
        with open(tmp_state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        os.remove(tmp_state_file)
    # note: if there were multiple files extracted from the image, they will remain in the workdir (resp. out_dir)
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
                return
            # push failed probably, because of a conflict (we could parse the stderr of git push to be sure)
            # let's try to fetch the latest
            if not self._fetch():
                # execute error, retry the whole sequence
                continue
            if not self._rebase():
                # git rebase should normally never fail
                # (if there is nothing to rebase it should also exit with code 0)
                raise RuntimeError('git rebase failed')
            # continue with attempting to push
            continue
        raise RuntimeError(f'push_changes failed (max_retries={max_retries})')

    def commit_and_push_if_needed(self, max_retries: int = 3) -> None:
        if self.commit():
            self.push_changes(max_retries=max_retries)

    pass


class ParticipantBase(ABC):

    def __init__(
        self,
        workdir: str,
        gist: str,
        token: str,
        author: Optional[str] = None,
        recreate_workdir: bool = False,
        skip_init_reset: bool = False,
        skip_init_pull: bool = False,
    ) -> None:
        self._workdir = os.path.abspath(workdir)
        self._gist = gist
        self._token = token
        self._recreate_workdir = recreate_workdir
        self._skip_init_reset = skip_init_reset
        self._skip_init_pull = skip_init_pull

        self._lib_client = GithubGistClient(
            gist=IMAGES_LIBRARY,
            repo_dir=os.path.join(self._workdir, 'lib'),
        )

        self._comm_client = GithubGistClient(
            gist=self._gist,
            token=self._token,
            repo_dir=os.path.join(self._workdir, 'comm'),
            author=author,
        )

    def _ensure_workdir(self) -> None:
        if os.path.isdir(self._workdir) and self._recreate_workdir:
            print(f'{gray}removing and re-creating workdir {magenta}{self._workdir}{gray}...{rst}')
            shutil.rmtree(self._workdir)
        if not os.path.isdir(self._workdir):
            os.makedirs(self._workdir)
        os.chdir(self._workdir)
        print(f'{gray}workdir ready and set as the process current working dir{rst}')

    def _setup(self) -> None:
        self._ensure_workdir()

        print(f'{gray}initializing images library to...{rst}')
        self._lib_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )
        self._load_lib_images()

        print(
            f'{gray}initializing the gist from {magenta}{self._comm_client.get_https_url(with_token=False)}{gray}'
            f' to {magenta}{self._comm_client.get_repo_dir()}{gray} ...{rst}'
        )
        self._comm_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )
        pass

    def _load_lib_images(self):
        self._lib_images = set(filter(is_image, os.listdir('lib')))
        print(f'library contains {cyan}{len(self._lib_images)}{rst} images')
        # for img in self._lib_images:
        #     print(f'  {img}')
        if CONTROL_IMAGE not in self._lib_images:
            raise RuntimeError(f'Control image {CONTROL_IMAGE} is not the library!')

    def run(self) -> None:
        raise NotImplementedError('Not implemented!')

    pass
