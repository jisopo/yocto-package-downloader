import os
import os.path
import urllib
import tarfile
import re
import subprocess

from tqdm import tqdm
from smb.SMBHandler import SMBHandler

FILE_SERVER_ADDRESS = "file-server"
FILE_SERVER_IP_ADDRESS = "10.10.10.5"
FILE_SERVER_USER_NAME = "jisopo"
FILE_SERVER_FILE_NAME = "log.txt"
FILE_SERVER_PATH_FILE = "smb://{}/incoming/{}/{}".format(FILE_SERVER_ADDRESS, FILE_SERVER_USER_NAME, FILE_SERVER_FILE_NAME)
FILE_SERVER_ALT_PATH_FILE = "smb://{}/incoming/{}/{}".format(FILE_SERVER_IP_ADDRESS, FILE_SERVER_USER_NAME, FILE_SERVER_FILE_NAME)

DOWNLOAD_OUTPUT_DIRECTORY = "output"

URL_REGEX = r'(?i)\b((?:[a-z][\w-]+:(?:\/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}\/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’]))'
DOWNLOAD_FILENAME_REGEX = r'([a-zA-Z0-9: ._\/\-]+);downloadfilename=([^ ]+)([^\s`!()\[\]{};:\'"<>?«»“”‘’])'
GIT_URL_REGEX = r'([^;]+);?|protocol=([a-z]+)?|;?|branch=([a-z0-9.\-]+)'

DISABLE_SSL_VERIFICATION = True
GIT_DOWNLOAD_SUBMODULES = True

GIT_VERIFICATION = ""
if DISABLE_SSL_VERIFICATION:
    GIT_VERIFICATION = "-c http.sslVerify=false"

opener = urllib.request.build_opener(SMBHandler)
downloader = urllib.request.build_opener()
downloader.addheaders = [('User-agent', 'Mozilla/5.0')]
urllib.request.install_opener(downloader)

errors_list = []

class DownloadProgressBar(tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)

def is_download_folder_exists():
    if not os.path.exists(os.path.join(".", DOWNLOAD_OUTPUT_DIRECTORY)):
        os.makedirs(DOWNLOAD_OUTPUT_DIRECTORY)

    return

def download_url(url, output_path):
    try:
        if not os.path.exists(output_path):
            with DownloadProgressBar(unit='B', unit_scale=True,
                                     miniters=1, desc=url.split('/')[-1]) as t:
                urllib.request.urlretrieve(url, filename=output_path, reporthook=t.update_to)

    except urllib.error.HTTPError as ex:
        error_msg = "Unable to download {}. Error {}".format(url, ex)
        errors_list.append(error_msg)

    except urllib.error.URLError as ex:
        error_msg = "Unable to download {}. Error {}".format(url, ex)
        errors_list.append(error_msg)

def make_tarfile(output_filename, source_dir):
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=".")

def getDataFromLine(line):
    source_url = ""
    protocol = ""
    file_name = ""
    github_download_link = ""
    git_branch = None
    archive_name = ""
    folder_name = ""
    custom_file_name = ""
    download_filename_flag = False

    download_filename_regex_result = re.search(DOWNLOAD_FILENAME_REGEX, line)
    if download_filename_regex_result:
        custom_file_name = download_filename_regex_result.group(2)
        download_filename_flag = True
        line = download_filename_regex_result.group(1)

    source_url_regex_result = re.search(URL_REGEX, line)
    if source_url_regex_result:
        source_url = source_url_regex_result.group(1)
    
        if 'git://' in source_url:
            protocol = "git"

            git_regex_result = re.search(GIT_URL_REGEX, source_url)
            if git_regex_result:
                git_branch = git_regex_result.group(3)
                github_download_link = git_regex_result.group(1).replace("git://", "https://")
                archive_name = "git2_{}.tar.gz".format(git_regex_result.group(1).replace("git://", "").replace("/","."))
                folder_name = github_download_link.split('/')[-1].replace(".git", "")
        else:
            protocol = "http/https"

        if download_filename_flag:
            file_name = custom_file_name
        else:
            file_name = source_url.split('/')[-1]

    return source_url, protocol, file_name, github_download_link, git_branch, archive_name, folder_name

def checkForErrors():
    print("\n")

    for package in errors_list:
        print(package)

def main():
    data = ""

    try:
        fh = opener.open(FILE_SERVER_PATH_FILE)
        data = fh.read()
        fh.close()
    except:
        print("Unable to open file from file-server with domain name \"{}\" and full path \"{}\". Trying to access directly via IP \"{}\" and full path \"{}\"".format(FILE_SERVER_ADDRESS, 
                                                                                                                                                                       FILE_SERVER_PATH_FILE,
                                                                                                                                                                       FILE_SERVER_IP_ADDRESS, 
                                                                                                                                                                       FILE_SERVER_ALT_PATH_FILE))
        fh = opener.open(FILE_SERVER_ALT_PATH_FILE)
        data = fh.read()
        fh.close()
    
    yocto_fetch_log = data.decode('utf8')

    is_download_folder_exists()

    for line in yocto_fetch_log.splitlines():
        if 'Failed to fetch URL' in line:
            source_url, protocol, file_name, github_download_link, git_branch, archive_name, folder_name = getDataFromLine(line)

            git_command_line_base = "git {} -c core.fsyncobjectfiles=0 clone --bare --mirror {} {}".format(GIT_VERIFICATION, 
                                                                                                           github_download_link,
                                                                                                           "--recurse-submodules" if GIT_DOWNLOAD_SUBMODULES else "")

            git_command_line_no_branch = "{} {}".format(git_command_line_base, 
                                                        folder_name)

            if source_url == "":
                err_msg = "Unable to get url from {}".format(line)
                errors_list.append(err_msg)
                continue

            if protocol == 'git':
                if not os.path.exists(folder_name):
                    if git_branch is not None:
                        git_command_line_branch = "{} --branch {} {}".format(git_command_line_base, 
                                                                 git_branch, 
                                                                 folder_name)
                        try:
                            # --recurse-submodules добавлен с версии 2.13
                            # TODO:
                            # проверку на исключение что указанный branch не найден
                            print("Cloning {}".format(github_download_link))
                            subprocess.check_output(git_command_line_branch, shell=True)
                        except:
                            subprocess.check_output(git_command_line_no_branch, shell=True)
                    else:
                        subprocess.check_output(git_command_line_no_branch, shell=True)

                    print("creating archive {}".format(archive_name))
                    make_tarfile(archive_name, folder_name)

            else:
                download_url(source_url, os.path.join(DOWNLOAD_OUTPUT_DIRECTORY, file_name))

                continue

    checkForErrors()

main()

print("Done")
