import os
from socket import *
from os.path import join
from threading import Thread
import time
import struct
import argparse
import socket
import math


def _argparse():
    parse = argparse.ArgumentParser(description="输入目标IP地址")
    parse.add_argument("--ip", type=str, help="IP地址")
    return parse.parse_args()


p_IP = _argparse().ip
test_port = 27000
com_port = 21300
file_port = 22000
folder_port = 24000
ff_port=23000
recover_list = []
flist = []
main_dir = "share"
mtime_table = {}


# function used to make header
def make_header(flag, filename, size, position):
    header = flag + struct.pack("!H", len(filename.encode())) + filename.encode() + struct.pack("!I", size)+ struct.pack("!I", position)
    rheader = struct.pack("!I", len(header)) + header
    return rheader


# function to unpack header after receive
def unpack_header(socket):
    msglength = socket.recv(4)
    length = struct.unpack("!I", msglength)[0]  # length of portocol
    msg1 = socket.recv(length)  # protocol
    msg = struct.unpack("!HH", msg1[0:4])
    filelength = struct.unpack("!H", msg1[4:6])[0]
    filename = msg1[6:6 + filelength].decode()
    size = struct.unpack("!I", msg1[6 + filelength:10 + filelength])[0]
    pos = struct.unpack("!I", msg1[10 + filelength:])[0]
    header = [msg, filename, size, pos]
    return header


# function to divide the file into blocks
def get_file_block(file_name, file_size, block_index, pos):
    block_size = math.ceil(file_size / 50)
    f = open(join(main_dir, file_name), 'rb')
    f.seek(block_index * block_size + pos) # pos is used for resend
    block = f.read(block_size)
    f.close()
    return block


# send single file function
def sendfile(main_dir1, filename, IP, port, pos):
    send_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            send_socket.connect((p_IP, port))
            break
        except:
            time.sleep(0.005)
    size = os.path.getsize(os.path.join(main_dir1, filename))
    # if files are too small
    if size < 2048:
        f = open(os.path.join(main_dir1, filename), "rb")
        send_socket.send(f.read())
        f.close()
    else:
        for i in range(50):
            send_socket.send(get_file_block(filename, size, i, pos))  # send file content
    send_socket.close()


# send folder function
def sendfolder(filename, IP, port):
    folder = os.path.join(main_dir, filename)
    filelist = os.listdir(folder)
    send_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    send_socket.connect((p_IP, folder_port))
    size = len(",".join(filelist).encode())
    msg = struct.pack("I", size)
    send_socket.send(msg)
    send_socket.send(",".join(filelist).encode())
    port=ff_port
    for file in filelist:
        port = port + 1  # use different ports
        time.sleep(0.01)  # sleep a little time to wait
        sendfile(folder, file, p_IP, port, 0)


# receive folder function
def receive_folder(filename, IP, port):
    folder_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    folder_socket.bind(("", folder_port))  # create receive socket
    folder_socket.listen(3)
    usss, addr = folder_socket.accept()
    length = struct.unpack("I", usss.recv(4))[0]
    filelist = usss.recv(length).decode().split(",")
    folder = os.path.join(main_dir, "120" + filename)
    port = ff_port
    for file in filelist:
        port = port + 1   # correspond to send folder
        f = open(os.path.join(folder, "120" + file), "wb")
        receive_file(f, IP, port, file, filename)


# receive single file function
def receive_file(f, IP, port, filename, folder):
    rev11_file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rev11_file_socket.bind(("", port))     # create receive socket
    rev11_file_socket.listen(3)
    rfilesocket, addr = rev11_file_socket.accept()
    while True:
        text = rfilesocket.recv(204800*20)
        f.write(text)
        if text == b'':
            break
    f.close()
    rev11_file_socket.close()
    # change name if finish receive
    if "120" + filename not in mtime_table.keys():
        if folder == "":
            os.rename(os.path.join(main_dir, "120" + filename), os.path.join(main_dir, filename))
            mtime_table[filename] = os.stat(os.path.join(main_dir, filename)).st_mtime
            print(mtime_table)  # check mtime
        else:
            re_dir = os.path.join(main_dir, "120" + folder)
            os.rename(os.path.join(re_dir, "120" + filename), os.path.join(re_dir, filename))


# get file size
def get_filesize(path):
    length = os.path.getsize(path)
    return length


# Thread 1: detecting new files and broadcast
def detnew():
    print("start detect")
    for file in os.listdir(main_dir):
        if not os.path.isdir(os.path.join(main_dir, file)):
            # update mtime after receive
            if file[0:3] != "120":
                mtime_table[file] = os.stat(os.path.join(main_dir, file)).st_mtime
    while True:
        # sleep to avoid memory occupy
        time.sleep(0.01)
        # traverse the share folder to find new file
        nowlist = os.listdir(main_dir)
        if len(nowlist) > len(flist):
            for file in nowlist:
                if file.startswith("120"):
                    if file[3:] not in flist:
                        flist.append(file[3:])
                else:
                    if (os.path.isdir(os.path.join(main_dir, file))):
                        time.sleep(3.5)  # make communications in order
                        print("need to sleep")
                    if file not in flist:
                        if findonline() == 0:
                            print("find new file " + file)
                            time.sleep(0.001)
                            broad(file)
                            flist.append(file)

        # traverse the mtime of files to detect update
        for file in mtime_table:
            if mtime_table[file] * 10 != os.stat(os.path.join(main_dir, file)).st_mtime * 10:
                update(file)
                mtime_table[file] = os.stat(os.path.join(main_dir, file)).st_mtime


# send update header
def update(file):
    print("send update out for " + file)
    flag = struct.pack("!HH", 5, 0)   # 5 means update
    header = make_header(flag, file, os.path.getsize(os.path.join(main_dir, file)), 0)
    upd_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upd_socket.connect((p_IP,com_port))
    upd_socket.send(header)
    upd_socket.close()


# broadcast new files to peer
def broad(file):
    print("broadcast" + file + " to " + p_IP)
    bro_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bro_socket.connect((p_IP,com_port))
    if os.path.isdir(os.path.join(main_dir, file)):
        flag = struct.pack("!HH", 1, 0)
    else:
        flag = struct.pack("!HH", 1, 1)
    size = os.path.getsize(os.path.join(main_dir, file))
    bro_socket.send(make_header(flag, file, size, 0))
    bro_socket.close()


# create share folder
def creshare(main_dir):
    if not os.path.exists(main_dir):
        os.makedirs(main_dir)


# make resend header and send to peer
def resend(filename):
    print("Start to resend")  # 4 means resend
    header = make_header(struct.pack("!HH", 4, 1), filename, os.path.getsize(os.path.join(main_dir, filename)), 0)
    res_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            res_socket.connect((p_IP, com_port))
            break
        except:
            time.sleep(0.005)
    res_socket.send(header)
    res_socket.close()


# Thread 2: used to receive headers if peer send header
def receive():
    # make the port reusable
    with socket.socket() as rev_socket:
        rev_socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        rev_socket.bind(("", com_port))
        rev_socket.listen(3)

        while True:
            send_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ussocket, addr = rev_socket.accept()
            info = unpack_header(ussocket)
            msg = info[0]
            filename = info[1]
            size = info[2]
            pos = info[3]
            # receive update from peer
            if msg[0] == 5:
                print("detect update for " + filename)
                flag = struct.pack("!HH", 0, 1)
                send_socket.connect((p_IP, com_port))
                # delete local file
                os.remove(os.path.join(main_dir, filename))
                # request new file
                send_socket.send(make_header(flag, filename, size, 0))
                f = open(os.path.join(main_dir, "120" + filename), "wb")
                receive_file(f, p_IP, file_port, filename, "")

            # receive resend header
            if msg[0] == 4:
                if msg[1] == 1:
                    # get the size which has been received
                    pos = os.path.getsize(os.path.join(main_dir, "120" + filename))
                    # request file
                    flag = struct.pack("!HH", 0, 1)
                    send_socket.connect((p_IP, com_port))
                    send_socket.send(make_header(flag, filename, size, pos))
                    # continue to receive
                    f = open(os.path.join(main_dir, "120" + filename), "ab")
                    receive_file(f, p_IP, file_port, filename, "")

            # receive request header
            if msg[0] == 0:
                print("receive request start to send")
                if msg[1] == 1:
                    time.sleep(0.001)
                    try:
                        sendfile(main_dir, filename, p_IP, file_port, pos)
                    except Exception as e:
                        # detect other peer has been killed
                        while True:
                            if findonline() == 0: # other peer restart
                                resend(filename)
                                break
                if msg[1] == 0:
                    time.sleep(0.05)
                    # send folder
                    sendfolder(filename, p_IP, folder_port)

            # receive broad header
            # start to receive
            if msg[0] == 1:
                print("find file start to check if need")
                print(flist)
                # check if have: if not have:
                if filename not in flist:
                    flist.append(filename)
                    # need to share
                    if msg[1] == 1:
                        print("file is single file")
                        send_socket.connect((p_IP, com_port))
                        # request file
                        send_socket.send(make_header(struct.pack("!HH", 0, 1), filename, size, 0))
                        f = open(os.path.join(main_dir, "120" + filename), "wb")
                        receive_file(f, "", file_port, filename, "")
                        flist.append(filename)
                        send_socket.close()
                    else:
                        print("file is folder")
                        os.path.exists(os.path.join(main_dir, "120" + filename))
                        os.makedirs(os.path.join(main_dir, "120" + filename))
                        # request file
                        send_socket.connect((p_IP, com_port))
                        send_socket.send(make_header(struct.pack("!HH", 0, 0), filename, 0, 0))
                        send_socket.close()
                        receive_folder(filename, p_IP, folder_port)
                        os.rename(os.path.join(main_dir, "120" + filename), os.path.join(main_dir, filename))


# test whether peer online
def findonline():
    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        test_socket.connect((p_IP, test_port))
        test_socket.close()
        return 0
    except Exception as e:
        return 1


# Thread 3: a testing socket for peer to test
def com_revive():
    print("start")
    com_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    com_socket.bind(("", test_port))
    com_socket.listen(3)
    print("set")
    while True:
        ussocket, addr = com_socket.accept()


def main():
    creshare(main_dir)
    com_thread = Thread(target=com_revive)
    com_thread.start()
    receive_thread = Thread(target=receive)
    receive_thread.start()
    detect_send_thread1 = Thread(target=detnew)
    detect_send_thread1.start()


if __name__ == '__main__':
    main()
