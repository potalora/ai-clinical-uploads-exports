"""IHE XDM METADATA.XML parser.

Parses ebXML registry manifests from IHE Cross-Enterprise Document Media
Interchange (XDM) packages to extract document inventory and patient
demographics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)

# ebXML namespaces used in IHE XDM manifests.
NS_RIM = "urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0"
NS_LCM = "urn:oasis:names:tc:ebxml-regrep:xsd:lcm:3.0"
NS = {"rim": NS_RIM, "lcm": NS_LCM}

# Classification scheme for author institution.
AUTHOR_CLASSIFICATION_SCHEME = "urn:uuid:93606bcf-9494-43ec-9b4e-a7748d1a838d"


@dataclass
class XDMDocument:
    """A single document entry from the XDM manifest."""

    uri: str
    hash: str
    size: int
    creation_time: str
    mime_type: str
    author_institution: str = ""


@dataclass
class XDMManifest:
    """Parsed contents of an IHE XDM METADATA.XML file."""

    documents: list[XDMDocument] = field(default_factory=list)
    patient_id: str | None = None
    patient_name: str | None = None
    patient_dob: str | None = None


def _get_slot_value(extrinsic: etree._Element, slot_name: str) -> str | None:
    """Extract the first Value from a named Slot element.

    Args:
        extrinsic: The ExtrinsicObject element to search within.
        slot_name: The name attribute of the Slot to find.

    Returns:
        The text content of the first Value element, or None.
    """
    slot = extrinsic.find(f"rim:Slot[@name='{slot_name}']/rim:ValueList/rim:Value", NS)
    if slot is not None and slot.text:
        return slot.text
    return None


def _get_slot_values(extrinsic: etree._Element, slot_name: str) -> list[str]:
    """Extract all Values from a named Slot element.

    Args:
        extrinsic: The ExtrinsicObject element to search within.
        slot_name: The name attribute of the Slot to find.

    Returns:
        List of text content from all Value elements.
    """
    values = extrinsic.findall(
        f"rim:Slot[@name='{slot_name}']/rim:ValueList/rim:Value", NS
    )
    return [v.text for v in values if v.text]


def _extract_patient_info(
    extrinsic: etree._Element,
) -> tuple[str | None, str | None, str | None]:
    """Extract patient demographics from sourcePatientInfo PID fields.

    Parses PID-3 (patient ID), PID-5 (name), and PID-7 (DOB) from the
    sourcePatientInfo slot values.

    Args:
        extrinsic: The ExtrinsicObject element containing patient info.

    Returns:
        Tuple of (patient_id, patient_name, patient_dob).
    """
    patient_id: str | None = None
    patient_name: str | None = None
    patient_dob: str | None = None

    info_values = _get_slot_values(extrinsic, "sourcePatientInfo")
    for val in info_values:
        if val.startswith("PID-3|"):
            patient_id = val.split("|", 1)[1]
        elif val.startswith("PID-5|"):
            raw_name = val.split("|", 1)[1]
            # Strip trailing empty components (e.g. "Doe^Jane^^^^" -> "Doe^Jane")
            patient_name = raw_name.rstrip("^")
        elif val.startswith("PID-7|"):
            patient_dob = val.split("|", 1)[1]

    return patient_id, patient_name, patient_dob


def _extract_author_institution(extrinsic: etree._Element) -> str:
    """Extract author institution from the Classification element.

    Looks for a Classification with the author classification scheme and
    extracts the authorInstitution slot value.

    Args:
        extrinsic: The ExtrinsicObject element to search within.

    Returns:
        The institution name, or empty string if not found.
    """
    classifications = extrinsic.findall("rim:Classification", NS)
    for cls in classifications:
        scheme = cls.get("classificationScheme", "")
        if scheme == AUTHOR_CLASSIFICATION_SCHEME:
            slot = cls.find(
                "rim:Slot[@name='authorInstitution']/rim:ValueList/rim:Value", NS
            )
            if slot is not None and slot.text:
                return slot.text
    return ""


def parse_xdm_metadata(metadata_path: Path) -> XDMManifest | None:
    """Parse an IHE XDM METADATA.XML file.

    Extracts document inventory (URIs, hashes, sizes, mime types) and
    patient demographics from the ebXML registry manifest.

    Args:
        metadata_path: Path to the METADATA.XML file.

    Returns:
        Parsed XDMManifest, or None if the file is missing or malformed.
    """
    if not metadata_path.exists():
        logger.warning("METADATA.XML not found at %s", metadata_path)
        return None

    try:
        tree = etree.parse(str(metadata_path))  # noqa: S320
    except etree.XMLSyntaxError:
        logger.warning("Malformed XML in %s", metadata_path)
        return None

    root = tree.getroot()
    manifest = XDMManifest()

    extrinsic_objects = root.findall(".//rim:ExtrinsicObject", NS)
    if not extrinsic_objects:
        logger.warning("No ExtrinsicObject elements found in %s", metadata_path)
        return manifest

    for ext_obj in extrinsic_objects:
        uri = _get_slot_value(ext_obj, "URI") or ""
        doc_hash = _get_slot_value(ext_obj, "hash") or ""
        size_str = _get_slot_value(ext_obj, "size") or "0"
        creation_time = _get_slot_value(ext_obj, "creationTime") or ""
        mime_type = ext_obj.get("mimeType", "")
        author_institution = _extract_author_institution(ext_obj)

        try:
            size = int(size_str)
        except ValueError:
            size = 0

        doc = XDMDocument(
            uri=uri,
            hash=doc_hash,
            size=size,
            creation_time=creation_time,
            mime_type=mime_type,
            author_institution=author_institution,
        )
        manifest.documents.append(doc)

        # Extract patient info from the first ExtrinsicObject that has it.
        if manifest.patient_id is None:
            pat_id, pat_name, pat_dob = _extract_patient_info(ext_obj)
            if pat_id:
                manifest.patient_id = pat_id
            if pat_name:
                manifest.patient_name = pat_name
            if pat_dob:
                manifest.patient_dob = pat_dob

    return manifest
