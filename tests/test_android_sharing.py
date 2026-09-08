from __future__ import annotations

import sys
import configparser
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "android" / "app"))

from moontransfer.cancellation import OperationCancelled
from moontransfer_android import sharing, storage
from tests.test_android_storage import (
    _ClipData, _MultiResolver, _SourceDocumentsContract, _SourceTreeResolver,
    _Uri, _tree_row,
)

CODE = "0123456789abcdef0123456789abcdef"
OTHER_CODE = "abcdef0123456789abcdef0123456789"


def intent(*, action=sharing.ACTION_SEND, streams=(), clip=(), text=None, texts=None, clip_texts=None):
    result = Mock()
    result.getAction.return_value = action
    result.getParcelableExtra.return_value = _Uri(streams[0]) if streams else None
    result.getParcelableArrayListExtra.return_value = None
    result.getCharSequenceArrayListExtra.return_value = None
    if action == sharing.ACTION_SEND_MULTIPLE:
        values = Mock()
        values.size.return_value = len(streams)
        values.get.side_effect = lambda i: _Uri(streams[i])
        result.getParcelableArrayListExtra.return_value = values
    result.getClipData.return_value = _ClipData(tuple(_Uri(u) for u in clip)) if clip else None
    result.getCharSequenceExtra.return_value = text
    if texts is not None:
        values = Mock()
        values.size.return_value = len(texts)
        values.get.side_effect = lambda i: texts[i]
        result.getCharSequenceArrayListExtra.return_value = values
    if clip_texts is not None:
        items = []
        for value in clip_texts:
            item = Mock()
            item.getUri.return_value = None
            item.getText.return_value = value
            items.append(item)
        data = Mock()
        data.getItemCount.return_value = len(items)
        data.getItemAt.side_effect = lambda i: items[i]
        result.getClipData.return_value = data
    return result


class AndroidSharingTests(unittest.TestCase):
    def test_generated_message_roundtrips(self):
        self.assertEqual(sharing.codes_from_shared_text(sharing.shared_code_message(CODE)), (CODE,))

    def test_formatted_and_uppercase_code(self):
        value = " ".join(CODE[i:i + 8] for i in range(0, 32, 8)).upper()
        self.assertEqual(sharing.codes_from_shared_text(value), (CODE,))

    def test_ambiguous_codes_remain_distinct(self):
        self.assertEqual(sharing.codes_from_shared_text(f"{CODE} {OTHER_CODE} {CODE}"), (CODE, OTHER_CODE))

    def test_invalid_or_oversized_text_is_rejected(self):
        for value in ("ciao", "x" + CODE, CODE + "0", "a" * 8193):
            with self.subTest(value=value[:40]), self.assertRaises(sharing.AndroidShareError):
                sharing.codes_from_shared_text(value)

    def test_launcher_intent_is_ignored(self):
        self.assertIsNone(sharing.read_shared_intent(intent(action="android.intent.action.MAIN")))

    def test_text_share_extracts_code(self):
        result = sharing.read_shared_intent(intent(text=sharing.shared_code_message(CODE)))
        self.assertEqual(result.codes, (CODE,))
        self.assertFalse(result.uris)

    def test_java_charsequence_is_converted_using_its_text(self):
        text = Mock()
        text.toString.return_value = CODE
        self.assertEqual(sharing.read_shared_intent(intent(text=text)).codes, (CODE,))

    def test_stream_takes_precedence_over_caption(self):
        result = sharing.read_shared_intent(intent(streams=("content://photos/1",), text=CODE))
        self.assertEqual(result.uris, ("content://photos/1",))
        self.assertFalse(result.codes)

    def test_multiple_texts_extract_code_from_instructions_and_code(self):
        incoming = intent(action=sharing.ACTION_SEND_MULTIPLE, texts=("Codice MoonTransfer:", CODE))
        self.assertEqual(sharing.read_shared_intent(incoming).codes, (CODE,))

    def test_clipdata_text_and_java_charsequence_are_supported(self):
        java_text = Mock()
        java_text.toString.return_value = CODE
        incoming = intent(clip_texts=("Codice MoonTransfer:", java_text))
        self.assertEqual(sharing.read_shared_intent(incoming).codes, (CODE,))

    def test_repeated_and_conflicting_codes_across_text_sources(self):
        for extra in (CODE, OTHER_CODE):
            with self.subTest(extra=extra):
                incoming = intent(action=sharing.ACTION_SEND_MULTIPLE, texts=(CODE,), clip_texts=(extra,))
                expected = (CODE,) if extra == CODE else (CODE, OTHER_CODE)
                self.assertEqual(sharing.read_shared_intent(incoming).codes, expected)

    def test_multiple_text_limits_apply_to_combined_content_and_item_count(self):
        for texts in (("a" * 4096, "b" * 4096), (CODE,) * 257):
            with self.subTest(count=len(texts)), self.assertRaises(sharing.AndroidShareError):
                sharing.read_shared_intent(intent(action=sharing.ACTION_SEND_MULTIPLE, texts=texts))

    def test_clipdata_cannot_bypass_combined_text_limit(self):
        incoming = intent(text="a" * 4096, clip_texts=("b" * 4096,))
        with self.assertRaises(sharing.AndroidShareError):
            sharing.read_shared_intent(incoming)

    def test_files_take_precedence_over_multiple_and_clipdata_texts(self):
        incoming = intent(action=sharing.ACTION_SEND_MULTIPLE,
                          streams=("content://files/1",), texts=(CODE, OTHER_CODE),
                          clip_texts=("x" * 9000,))
        result = sharing.read_shared_intent(incoming)
        self.assertEqual(result.uris, ("content://files/1",))
        self.assertFalse(result.codes)

    def test_code_fragments_in_separate_items_are_not_joined_into_a_code(self):
        incoming = intent(action=sharing.ACTION_SEND_MULTIPLE, texts=(CODE[:16], CODE[16:]))
        with self.assertRaises(sharing.AndroidShareError):
            sharing.read_shared_intent(incoming)

    def test_multiple_streams_and_clipdata_are_deduplicated(self):
        result = sharing.read_shared_intent(intent(
            action=sharing.ACTION_SEND_MULTIPLE,
            streams=("content://files/1", "content://files/2"),
            clip=("content://files/1", "content://files/3"),
        ))
        self.assertEqual(result.uris, ("content://files/1", "content://files/2", "content://files/3"))

    def test_clipdata_only_share(self):
        self.assertEqual(sharing.read_shared_intent(intent(clip=("content://files/1",))).uris,
                         ("content://files/1",))

    def test_non_content_uris_and_empty_shares_are_rejected(self):
        for value in ("file:///data/data/private", "https://example.org/a", "content:///missing"):
            with self.subTest(uri=value), self.assertRaises(sharing.AndroidShareError):
                sharing.read_shared_intent(intent(streams=(value,)))
        with self.assertRaises(sharing.AndroidShareError):
            sharing.read_shared_intent(intent())

    def test_excessive_stream_count_is_rejected_before_reading(self):
        incoming = intent(action=sharing.ACTION_SEND_MULTIPLE, streams=("content://files/1",) * 257)
        with self.assertRaises(sharing.AndroidShareError):
            sharing.read_shared_intent(incoming)
        incoming.getParcelableArrayListExtra.return_value.get.assert_not_called()

    def test_manifest_advertises_single_and_multiple_sharing(self):
        root = ET.fromstring("<filters>" + (ROOT / "android/share_intent_filters.xml").read_text() + "</filters>")
        ns = "{http://schemas.android.com/apk/res/android}"
        self.assertEqual({n.attrib[ns + "name"] for n in root.iter("action")},
                         {sharing.ACTION_SEND, sharing.ACTION_SEND_MULTIPLE})
        self.assertTrue(all(n.attrib[ns + "mimeType"] == "*/*" for n in root.iter("data")))

    def test_build_launches_the_share_aware_activity(self):
        config = configparser.ConfigParser()
        config.read(ROOT / "android/buildozer.spec")
        self.assertEqual(config["app"]["android.entrypoint"],
                         "io.github.gaumeloth.moontransfer.MoonTransferActivity")
        self.assertEqual(config["app"]["android.manifest.launch_mode"], "singleTask")
        self.assertTrue((ROOT / "android" / config["app"]["android.manifest.intent_filters"]).is_file())


class SharedStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.write_bytes(b"shared contents")
        self.staging = self.root / "staging"
        self.contract = Mock()
        self.contract.isTreeUri.return_value = False

    def stage(self, values, resolver, **kwargs):
        return sharing.stage_shared_uris(
            values, self.staging, resolver=resolver,
            documents_contract=self.contract, uri_parser=lambda value: value, **kwargs,
        )

    def resolver(self, sources):
        resolver = _MultiResolver(sources)
        resolver.getType = lambda uri: "application/octet-stream"
        return resolver

    def test_shared_files_are_copied_and_existing_selection_is_preserved(self):
        resolver = self.resolver({"content://f/a": (self.source, "a.txt"), "content://f/b": (self.source, "b.txt")})
        existing = self.stage(("content://f/a",), resolver)
        added = self.stage(("content://f/b",), resolver, existing_selection=existing)
        self.assertEqual(added.root_paths[0].read_bytes(), self.source.read_bytes())
        self.assertEqual(existing.root_paths[0].read_bytes(), self.source.read_bytes())
        self.assertEqual(existing.merged_with(added).count, 2)

    def test_failed_batch_removes_partial_import_but_preserves_existing(self):
        resolver = self.resolver({"content://f/a": (self.source, "a.txt"), "content://f/b": (self.source, "b.txt")})
        existing = self.stage(("content://f/a",), resolver)
        before = set(self.staging.iterdir())
        with self.assertRaises(Exception):
            self.stage(("content://f/b", "content://f/missing"), resolver, existing_selection=existing)
        self.assertEqual(set(self.staging.iterdir()), before)
        self.assertTrue(existing.root_paths[0].exists())

    def test_duplicate_names_roll_back_the_entire_batch(self):
        resolver = self.resolver({"content://f/a": (self.source, "same"), "content://f/b": (self.source, "same")})
        with self.assertRaises(storage.AndroidStorageError):
            self.stage(("content://f/a", "content://f/b"), resolver)
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_non_tree_folder_offers_picker_fallback(self):
        resolver = Mock()
        resolver.getType.return_value = storage.DIRECTORY_MIME_TYPE
        with self.assertRaises(sharing.SharedDirectoryAccessError):
            self.stage(("content://files/directory",), resolver)

    def test_cancellation_is_not_reported_as_a_folder_permission_error(self):
        with self.assertRaises(OperationCancelled):
            self.stage(("content://files/directory",), Mock(), cancel_requested=lambda: True)

    def test_shared_subdirectory_does_not_import_its_parent_tree(self):
        self.contract = _SourceDocumentsContract()
        self.contract.isTreeUri = lambda _: True
        self.contract.getDocumentId = lambda _: "sub"
        resolver = _SourceTreeResolver({
            "document:sub": (_tree_row("sub", "Selected", storage.DIRECTORY_MIME_TYPE),),
            "children:sub": (_tree_row("file", "data.txt", "text/plain", size=15),),
        }, {"document:file": self.source})
        resolver.getType = lambda _: storage.DIRECTORY_MIME_TYPE
        added = self.stage(("content://files/tree/root/document/sub",), resolver)
        self.assertEqual(added.filenames, ("Selected",))
        self.assertEqual((added.root_paths[0] / "data.txt").read_bytes(), b"shared contents")
