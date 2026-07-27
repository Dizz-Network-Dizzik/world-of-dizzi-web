"""Geteilter XML-Schutz (docs/50 P4.1): DTD/Entities abweisen ⇒ kein XXE, keine
Billion-Laughs-Bombe; gültiges XML parst normal weiter."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from appkit.xml_safe import UnsicheresXml, pruefe_keine_dtd, sichere_wurzel


def test_billion_laughs_abgewiesen():
    bombe = ('<?xml version="1.0"?>'
             '<!DOCTYPE lolz [<!ENTITY a "AAAAAAAAAA">'
             '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
             '<root><x>&b;</x></root>')
    with pytest.raises(UnsicheresXml):
        sichere_wurzel(bombe)


def test_xxe_externe_entitaet_abgewiesen():
    xxe = ('<?xml version="1.0"?>'
           '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
           '<root>&xxe;</root>')
    with pytest.raises(UnsicheresXml):
        sichere_wurzel(xxe)


def test_utf16_geschmuggelte_dtd_abgewiesen():
    # NUL-Strip ⇒ auch UTF-16-kodierte <!DOCTYPE-Marker werden erkannt
    roh = '<!DOCTYPE x [<!ENTITY e "x">]><root/>'.encode("utf-16")
    with pytest.raises(UnsicheresXml):
        pruefe_keine_dtd(roh)


def test_gueltiges_xml_parst_normal():
    root = sichere_wurzel('<root><a>1</a><b>2</b></root>')
    assert root.tag == "root"
    assert [int(k.text) for k in root] == [1, 2]
    # bytes-Eingabe + Encoding-Deklaration
    root2 = sichere_wurzel('<?xml version="1.0" encoding="utf-8"?><r x="ä"/>'.encode("utf-8"))
    assert root2.get("x") == "ä"


def test_kaputtes_xml_reicht_parseerror_durch():
    with pytest.raises(ET.ParseError):
        sichere_wurzel("<root><offen>")
