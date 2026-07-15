import io
from pathlib import Path

import pytest

from app.storage import LocalStorage, S3Storage


class TestLocalStorage:
    def test_save_read_delete_roundtrip(self, tmp_path):
        storage = LocalStorage(root=tmp_path)
        storage.save("ws1/doc1_test.txt", b"hello")

        with storage.local_path("ws1/doc1_test.txt") as path:
            assert path.read_bytes() == b"hello"

        storage.delete("ws1/doc1_test.txt")
        assert not (tmp_path / "ws1/doc1_test.txt").exists()

    def test_delete_missing_is_noop(self, tmp_path):
        LocalStorage(root=tmp_path).delete("nope/missing.txt")

    def test_save_creates_parent_dirs(self, tmp_path):
        storage = LocalStorage(root=tmp_path)
        storage.save("a/b/c.txt", b"x")
        assert (tmp_path / "a/b/c.txt").read_bytes() == b"x"


class FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def download_fileobj(self, Bucket, Key, Fileobj):
        if (Bucket, Key) not in self.objects:
            raise RuntimeError("NoSuchKey")
        Fileobj.write(self.objects[(Bucket, Key)])


class TestS3Storage:
    def test_save_read_delete_roundtrip(self):
        client = FakeS3Client()
        storage = S3Storage(client=client, bucket="b")
        storage.save("ws1/doc1_test.pdf", b"pdfbytes")
        assert client.objects[("b", "ws1/doc1_test.pdf")] == b"pdfbytes"

        with storage.local_path("ws1/doc1_test.pdf") as path:
            assert path.read_bytes() == b"pdfbytes"
            # parsers dispatch on suffix — temp file must preserve it
            assert path.suffix == ".pdf"
        assert not path.exists()  # temp file cleaned up

        storage.delete("ws1/doc1_test.pdf")
        assert client.objects == {}

    def test_delete_missing_is_noop(self):
        S3Storage(client=FakeS3Client(), bucket="b").delete("missing.txt")

    def test_local_path_missing_key_raises(self):
        storage = S3Storage(client=FakeS3Client(), bucket="b")
        with pytest.raises(RuntimeError):
            with storage.local_path("missing.txt"):
                pass
