#!/usr/bin/env python

#    Copyright (C) 2015  lazypeople  <hfutming@gmail.com>
#
#    This program can be distributed under the terms of the GNU LGPL.
#    See the file COPYING.
#

import os, stat, errno
# pull in some spaghetti to make this stuff work without fuse-py being installed
try:
    import _find_fuse_parts
except ImportError:
    pass
import fuse
from fuse import Fuse
from sinastorage.bucket import SCSBucket
import sinastorage
import datetime
import calendar
import tempfile

if not hasattr(fuse, '__version__'):
    raise RuntimeError, \
        "your fuse-py doesn't know of fuse.__version__, probably it's too old."

fuse.fuse_python_api = (0, 2)

scs_accesskey = '你的新浪云存储ak'
scs_secretkey = '你的新浪云存储sk'
scs_bucket = '你的bucket名'
sinastorage.setDefaultAppInfo(scs_accesskey, scs_secretkey)
s = SCSBucket(scs_bucket, secure=False)

def flag2mode(flags):
    md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]

    if flags | os.O_APPEND:
        m = m.replace('w', 'a', 1)

    return m

def download(path, tmp_path):
    if path.startswith('/'):
        path = path[1:]
    CHUNK = 16*1024
    response = s[path]
    with open(tmp_path, 'wb') as fp:
        while True:
            chunk = response.read(CHUNK)
            if not chunk: break
            fp.write(chunk)
        fp.close()
    return True

def writescs(path, tmp_path):
    if path.startswith('/'):
        path = path[1:]
    s.putFile(path, tmp_path)

class MyStat(fuse.Stat):
    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 501
        self.st_gid = 501
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0

class SinacloudFS(Fuse):
    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        self.files = {}

    def getattr(self, path):
        st = MyStat()
        if path.endswith('/'):
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 2
        else:
            # check file exists
            if path.startswith('/'):
                path = path[1:]
            try:
                finfo = s.info(path)
            except Exception, e:
                # try path.'/'
                path_retry = path+'/'
                try:
                    finfo_retry = s.info(path_retry)
                    st.st_mode = stat.S_IFDIR | 0755
                    st.st_nlink = 2
                    return st
                except Exception, e:
                    return -errno.ENOENT
            st.st_mode = stat.S_IFREG | 0755
            st.st_nlink = 1
            st.st_size = int(finfo['headers']['x-filesize'])
            # parse datetime
            timestamp = finfo['date']
            timestamp = int(calendar.timegm(timestamp.utctimetuple()))
            st.st_atime = timestamp
            st.st_mtime = timestamp 
            st.st_ctime = timestamp
        return st

    def readdir(self, path, offset):
        if path.startswith('/'):
            path = path[1:]
        if not path.endswith('/'):
            path = path+'/'
        if path == '/':
            path = ''
        path_len = len(path)
        for r in s.listdir(prefix=path, marker=None, limit=None, delimiter='/'):
            # if contain sub dir file,continue
            tmp_name = str(r[0])
            if len(tmp_name) == path_len:
                continue
            tmp_name = tmp_name[path_len:]
            length = len(r)
            if length == 2:
                tmp_name = tmp_name[:-1]
                yield fuse.Direntry(name=tmp_name, st_mode=stat.S_IFDIR | 0755, st_nlink=2)
            else:
                timestamp = r[4]
                timestamp = int(calendar.timegm(timestamp.utctimetuple()))
                length_file = int(r[8])
                yield fuse.Direntry(name=tmp_name, st_mode=stat.S_IFREG | 0755, st_nlink=1, st_size=length_file,st_atime=timestamp,st_mtime=timestamp,st_ctime=timestamp)

    def mkdir(self, path, mode):
        if path.startswith('/'):
            path = path[1:]
        if not path.endswith('/'):
            path = path+'/'
        
        try:
            finfo = s.info(path)
            return -errno.ENOTEMPTY
        except Exception, e:
            pass
        s.put(path, u'')

    def unlink(self, path):
        if path.startswith('/'):
            path = path[1:]
        del s[path]

    class XmpFile(object):

        def __init__(self, path, flags, *mode):
            (tmp_f, tmp_path) = tempfile.mkstemp(prefix='scs')
            os.close(tmp_f)
            try:
                download(path, tmp_path)
            except Exception, e:
                pass
            self.tmp_path = tmp_path
            self.path = path
            self.file = os.fdopen(os.open(tmp_path, flags, *mode),
                                  flag2mode(flags))
            self.fd = self.file.fileno()

        def read(self, length, offset):
            self.file.seek(offset)
            return self.file.read(length) 

        def write(self, buf, offset):
            self.file.seek(offset)
            self.file.write(buf)
            return len(buf)

        def release(self, flags):
            try:
                writescs(self.path, self.tmp_path)
            except Exception, e:
                pass
            self.file.close()
            os.unlink(self.tmp_path)

        def _fflush(self):
            if 'w' in self.file.mode or 'a' in self.file.mode:
                self.file.flush()

        def fsync(self, isfsyncfile):
            self._fflush()
            if isfsyncfile and hasattr(os, 'fdatasync'):
                os.fdatasync(self.fd)
            else:
                os.fsync(self.fd)

        def flush(self):
            self._fflush()
            # cf. xmp_flush() in fusexmp_fh.c
            os.close(os.dup(self.fd))

        def fgetattr(self):
            return os.fstat(self.fd)

        def ftruncate(self, len):
            self.file.truncate(len)

    def main(self, *a, **kw):

        self.file_class = self.XmpFile

        return Fuse.main(self, *a, **kw)

def main():
    usage="""
Mount SCS IN Userspace

""" + Fuse.fusage
    server = SinacloudFS(version="%prog " + fuse.__version__,
                     usage=usage,
                     dash_s_do='setsingle')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()