#!/usr/bin/python
#coding: utf-8
import requests
import xml.etree.ElementTree as ET


class YaDiskException(Exception):
    """Common exception class for YaDisk. Arg 'code' have code of HTTP Error."""
    code = None

    def __init__(self, code, text):
        super(YaDiskException, self).__init__(text)
        self.code = code

    def __str__(self):
        return "%d. %s" % (self.code, super(YaDiskException, self).__str__())


class YaDiskXML(object):
    namespaces = {'d': "DAV:"}

    def find(self, node, path):
        """Wrapper for lxml`s find."""

        return node.find(path, namespaces=self.namespaces)

    def xpath(self, node, path):
        """Wrapper for lxml`s xpath."""

        return node.xpath(path, namespaces=self.namespaces)


class YaDisk(object):
    """Main object for work with Yandex.disk."""

    login = None
    password = None
    url = "https://webdav.yandex.com/"
    namespaces = {'d': 'DAV:'}
    
    def __init__(self, login, password):
        super(YaDisk, self).__init__()
        self.login = login
        self.password = password
        if self.login is None or self.password is None:
            raise Exception("Please, set login and password to Yandex.Disk.")

    def _sendRequest(self, type, addUrl="/", addHeaders={}, data=None):
        headers = {"Accept": "*/*"}
        headers.update(addHeaders)
        url = self.url + addUrl
        req = requests.Request(type, url, headers=headers, auth=(self.login, self.password), data=data)
        with requests.Session() as s:
            return s.send(req.prepare())

    def ls(self, path, offset=None, amount=None):
        """
        Return list of files/directories. Each item is a dict. 
        Keys: 'path', 'creationdate', 'displayname', 'length', 'lastmodified', 'isDir'.
        """
        
        def parseContent(content):
            result = []
            root = ET.fromstring(content)
            for response in root.findall('.//d:response', namespaces=self.namespaces):
                node = {
                    'path': response.find("d:href", namespaces=self.namespaces).text,
                    'creationdate': response.find("d:propstat/d:prop/d:creationdate", namespaces=self.namespaces).text,
                    'displayname': response.find("d:propstat/d:prop/d:displayname", namespaces=self.namespaces).text,
                    'lastmodified': response.find("d:propstat/d:prop/d:getlastmodified", namespaces=self.namespaces).text,
                    'isDir': response.find("d:propstat/d:prop/d:resourcetype/d:collection", namespaces=self.namespaces) != None
                }
                if not node['isDir']:
                    node['length'] = response.find("d:propstat/d:prop/d:getcontentlength", namespaces=self.namespaces).text
                    node['etag'] = response.find("d:propstat/d:prop/d:getetag", namespaces=self.namespaces).text
                    node['type'] = response.find("d:propstat/d:prop/d:getcontenttype", namespaces=self.namespaces).text
                result.append(node)
            return result

        url = path
        if (offset != None) and (amount != None):
            url += "?offset=%d&amount=%d" % (offset, amount)
        resp = self._sendRequest("PROPFIND", path, {'Depth': 1})
        if resp.status_code == 207:
            return parseContent(resp.content)
        else:
            raise YaDiskException(resp.status_code, resp.content)

    def df(self):
        """Return dict with size of Ya.Disk. Keys: 'available', 'used'."""

        def parseContent(content):
            root = ET.fromstring(content)
            return {
                'available': root.find(".//d:quota-available-bytes", namespaces=self.namespaces).text, 
                'used': root.find(".//d:quota-used-bytes", namespaces=self.namespaces).text
            }

        data = """
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:quota-available-bytes/>
    <D:quota-used-bytes/>
  </D:prop>
</D:propfind>
        """
        resp = self._sendRequest("PROPFIND", "/", {'Depth': 0}, data)
        if resp.status_code == 207:
            return parseContent(resp.content)
        else:
            raise YaDiskException(resp.status_code, resp.content)

    def mkdir(self, path):
        """Create directory. All part of path must be exists. Raise exception when path already exists."""

        resp = self._sendRequest("MKCOL", path)
        if resp.status_code != 201:
            if resp.status_code == 409:
                raise YaDiskException(409, "Part of path %s does not exists" % path)
            elif resp.status_code == 405:
                raise YaDiskException(405, "Path %s already exists" % path)
            else:
                raise YaDiskException(resp.status_code, resp.content)

    def rm(self, path):
        """Delete file or directory."""

        resp = self._sendRequest("DELETE", path)
        # By documentation server must return 200 "OK", but I get 204 "No Content".
        # Anyway file or directory have been removed.
        if not (resp.status_code in [200, 204]):
            raise YaDiskException(resp.status_code, resp.content)

    def cp(self, src, dst):
        """Copy file or directory."""

        if dst[0] != '/':
            raise YaDiskException("Destination path must be absolute")
        resp = self._sendRequest("COPY", src, {'Destination': dst})
        if resp.status_code != 201:
            raise YaDiskException(resp.status_code, resp.content)

    def mv(self, src, dst):
        """Move file or directory."""

        if dst[0] != '/':
            raise YaDiskException("Destination path must be absolute")
        resp = self._sendRequest("MOVE", src, {'Destination': dst})
        if resp.status_code != 201:
            raise YaDiskException(resp.status_code, resp.content)

    def upload(self, file, path):
        """Upload file."""

        with open(file, "r") as f:
            resp = self._sendRequest("PUT", path, data=f.read())
            if resp.status_code != 201:
                raise YaDiskException(resp.status_code, resp.content)

    def download(self, path, file):
        """Download remote file to disk."""

        resp = self._sendRequest("GET", path)
        if resp.status_code == 200:
            with open(file, "wb") as f:
                f.write(resp.content)
        else:
            raise YaDiskException(resp.status_code, resp.content)
