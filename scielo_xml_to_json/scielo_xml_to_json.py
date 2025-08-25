#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SciELO JATS XML ➜ JSON (NDJSON) converter
-----------------------------------------
- Percorre pastas com XMLs do SciELO/JATS e gera NDJSON (1 JSON por linha)
- Extrai metadados (ids, títulos, autores, afiliações resolvidas, resumos, keywords)
- Extrai full_text e full_text_sections do <body>
- Extrai referências: mantém mixed_citation + structured (rica)
- Inclui article_type e article_category (heading)
- Opcional: inclui o XML bruto (--include-raw-xml)
- Opcional: gera arquivo _bulk do Elasticsearch (--bulk --index-name)

Uso:
    python scielo_xml_to_json.py \
      -i scielo/2025-08-22/XML \
      --out out/scielo.ndjson \
      --bulk out/scielo_bulk.jsonl \
      --index-name scielo
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree


# ---------------------- helpers ----------------------

def _txt(el: Optional[etree._Element]) -> Optional[str]:
    """Texto do elemento (itertext) com espaços colapsados; None se vazio."""
    if el is None:
        return None
    text = " ".join(" ".join(el.itertext()).split()).strip()
    return text or None


def _find(root: Optional[etree._Element], path: str, ns: Optional[Dict[str, str]] = None) -> Optional[etree._Element]:
    return root.find(path, namespaces=ns) if root is not None else None


def _findall(root: Optional[etree._Element], path: str, ns: Optional[Dict[str, str]] = None) -> List[etree._Element]:
    return list(root.findall(path, namespaces=ns)) if root is not None else []


def _prune(obj: Any) -> Any:
    """Remove None/[]/{} recursivamente (mantém 0/False)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v2 = _prune(v)
            if v2 is None or v2 == [] or v2 == {}:
                continue
            out[k] = v2
        return out
    if isinstance(obj, list):
        return [v for v in (_prune(v) for v in obj) if v is not None and v != [] and v != {}]
    return obj


# ---------------------- full text ----------------------

def _clean_text(el: etree._Element) -> str:
    return " ".join(" ".join(el.itertext()).split()).strip()


def extract_full_text(root: etree._Element) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Retorna (full_text, full_text_sections) a partir do <body>.
    full_text: str com todos os parágrafos.
    full_text_sections: lista de dicts {title, paragraphs}.
    """
    body = root.find("body")
    if body is None:
        return None, []

    sections: List[Dict[str, Any]] = []
    for sec in body.findall(".//sec"):
        title_el = sec.find("title")
        title = _clean_text(title_el) if title_el is not None else None
        paras = [_clean_text(p) for p in sec.findall("p")]
        paras = [p for p in paras if p]
        if title is None and not paras:
            continue
        sections.append({"title": title, "paragraphs": paras})

    all_paragraphs = [_clean_text(p) for p in body.findall(".//p")]
    all_paragraphs = [p for p in all_paragraphs if p]
    full_text = "\n\n".join(all_paragraphs) if all_paragraphs else None
    return full_text, sections


# ---------------------- parsing de blocos ----------------------

def parse_article(xml_path: Path, include_raw_xml: bool = False) -> Dict[str, Any]:
    parser = etree.XMLParser(recover=True, huge_tree=True)
    xml_bytes = xml_path.read_bytes()
    root = etree.fromstring(xml_bytes, parser=parser)
    ns = root.nsmap  # SciELO geralmente sem ns default; mantemos para compatibilidade

    record: Dict[str, Any] = {"source_file": str(xml_path)}

    # article-type no <article>
    article_type = root.get("article-type")
    if article_type:
        record["article_type"] = article_type

    # front / article-meta com checagem explícita (evita FutureWarning)
    front = _find(root, "front", ns)
    if front is None:
        front = root
    article_meta = _find(front, "article-meta", ns)
    if article_meta is None:
        article_meta = front

    # títulos e traduções
    title_group = _find(article_meta, "title-group", ns)
    if title_group is not None:
        record["article_title"] = _txt(_find(title_group, "article-title", ns))
        translations = []
        for alt in _findall(title_group, "trans-title-group", ns):
            translations.append(
                _prune(
                    {
                        "lang": alt.get("{http://www.w3.org/XML/1998/namespace}lang") or alt.get("xml:lang"),
                        "title": _txt(_find(alt, "trans-title", ns)) or _txt(_find(alt, "article-title", ns)),
                    }
                )
            )
        if translations:
            record["article_title_translated"] = translations

    # periódico
    journal_meta = _find(front, "journal-meta", ns)
    if journal_meta is not None:
        record["journal_title"] = _txt(_find(journal_meta, "journal-title", ns))
        record["journal_issn"] = _txt(_find(journal_meta, "issn", ns))
        record["journal_publisher"] = _txt(_find(journal_meta, "publisher/publisher-name", ns))

    # ids
    ids: Dict[str, str] = {}
    for aid in _findall(article_meta, "article-id", ns):
        pid_type = aid.get("pub-id-type")
        if pid_type:
            ids[pid_type] = (aid.text or "").strip()
    if ids:
        record["ids"] = ids
        if "doi" in ids:
            record["doi"] = ids["doi"]

    # categoria editorial (heading)
    cat_heading = _find(article_meta, ".//article-categories/subj-group[@subj-group-type='heading']/subject", ns)
    if cat_heading is not None:
        cat_txt = _txt(cat_heading)
        if cat_txt:
            record["article_category"] = cat_txt

    # autores e afiliações
    aff_map: Dict[str, Dict[str, Any]] = {}
    for aff in _findall(article_meta, "aff", ns):
        aff_id = aff.get("id")
        inst_original = _txt(_find(aff, "institution[@content-type='original']", ns))
        inst_normalized = _txt(_find(aff, "institution[@content-type='normalized']", ns))
        inst_orgname = _txt(_find(aff, "institution[@content-type='orgname']", ns))
        country = _txt(_find(aff, "country", ns))
        name_all = _txt(aff)
        aff_map[aff_id or f"aff_{len(aff_map)+1}"] = _prune(
            {
                "id": aff_id,
                "institution_original": inst_original,
                "institution_normalized": inst_normalized,
                "institution_orgname": inst_orgname,
                "institution": inst_normalized or inst_orgname or inst_original or name_all,
                "country": country,
                "name": name_all,
            }
        )

    contribs: List[Dict[str, Any]] = []
    for c in _findall(article_meta, "contrib-group/contrib", ns):
        if c.get("contrib-type") and c.get("contrib-type") != "author":
            continue
        given = _txt(_find(c, "name/given-names", ns))
        surname = _txt(_find(c, "name/surname", ns))
        email = _txt(_find(c, "email", ns))
        orcid_el = _find(c, "contrib-id[@contrib-id-type='orcid']", ns)
        orcid = (orcid_el.text or "").strip() if orcid_el is not None and orcid_el.text else None

        aff_ids: List[str] = []
        for xr in _findall(c, "xref", ns):
            if xr.get("ref-type") == "aff" and xr.get("rid"):
                aff_ids.append(xr.get("rid"))

        aff_objs = [aff_map.get(aid) for aid in aff_ids if aff_map.get(aid)]
        aff_names = []
        for ao in aff_objs:
            nice = ao.get("institution") or ao.get("name")
            if nice:
                aff_names.append(nice)

        contribs.append(
            _prune(
                {
                    "given": given,
                    "surname": surname,
                    "email": email,
                    "orcid": orcid,
                    "aff_ids": aff_ids or None,
                    "affiliations": aff_objs or None,
                    "affiliation_names": aff_names or None,
                }
            )
        )

    if contribs:
        record["authors"] = contribs
    if aff_map:
        record["affiliations"] = aff_map

    # resumos
    abstracts: List[Dict[str, Any]] = []
    for ab in _findall(article_meta, "abstract", ns):
        if ab.tag.endswith("abstract"):
            abstracts.append(
                _prune(
                    {
                        "lang": ab.get("{http://www.w3.org/XML/1998/namespace}lang") or ab.get("xml:lang"),
                        "text": _txt(ab),
                    }
                )
            )
    if abstracts:
        record["abstracts"] = abstracts

    # palavras‑chave
    kw_sets: List[Dict[str, Any]] = []
    for kwg in _findall(article_meta, "kwd-group", ns):
        lang = kwg.get("{http://www.w3.org/XML/1998/namespace}lang") or kwg.get("xml:lang")
        kws = [_txt(kw) for kw in _findall(kwg, "kwd", ns)]
        kws = [k for k in kws if k]
        if kws:
            kw_sets.append(_prune({"lang": lang, "keywords": kws}))
    if kw_sets:
        record["keywords"] = kw_sets

    # publicação
    pub_date = _find(article_meta, "pub-date", ns)
    if pub_date is not None:
        record["pub_date"] = _prune(
            {
                "pub_type": pub_date.get("pub-type"),
                "year": _txt(_find(pub_date, "year", ns)),
                "month": _txt(_find(pub_date, "month", ns)),
                "day": _txt(_find(pub_date, "day", ns)),
                "season": _txt(_find(pub_date, "season", ns)),
            }
        )
    record["volume"] = _txt(_find(article_meta, "volume", ns))
    record["issue"] = _txt(_find(article_meta, "issue", ns))
    record["fpage"] = _txt(_find(article_meta, "fpage", ns))
    record["lpage"] = _txt(_find(article_meta, "lpage", ns))

    # licença
    lic = _find(article_meta, "permissions/license", ns)
    if lic is not None:
        record["license"] = _prune(
            {
                "license_type": lic.get("license-type"),
                "href": lic.get("{http://www.w3.org/1999/xlink}href") or lic.get("xlink:href"),
                "text": _txt(_find(lic, "license-p", ns)) or _txt(lic),
            }
        )

    # full text
    full_text, full_text_sections = extract_full_text(root)
    record["full_text"] = full_text
    record["full_text_sections"] = full_text_sections

    # referências (superestruturadas)
    references: List[Dict[str, Any]] = []
    for ref in _findall(root, "back/ref-list/ref", ns):
        mixed = _txt(_find(ref, "mixed-citation", ns))
        ec = _find(ref, "element-citation", ns)
        structured: Dict[str, Any] = {}

        if ec is not None:
            structured["publication_type"] = ec.get("publication-type")

            # autores
            authors: List[Dict[str, Any]] = []
            for nm in _findall(ec, ".//person-group[@person-group-type='author']/name", ns):
                authors.append(
                    _prune(
                        {
                            "surname": _txt(_find(nm, "surname", ns)),
                            "given": _txt(_find(nm, "given-names", ns)),
                        }
                    )
                )
            if authors:
                structured["authors"] = authors

            # títulos e fonte
            structured["article_title"] = _txt(_find(ec, "article-title", ns))
            structured["source"] = _txt(_find(ec, "source", ns))
            structured["comment"] = _txt(_find(ec, "comment", ns))

            # editora e local
            structured["publisher_loc"] = _txt(_find(ec, "publisher-loc", ns))
            structured["publisher_name"] = _txt(_find(ec, "publisher-name", ns))

            # dados bibliográficos
            structured["year"] = _txt(_find(ec, "year", ns))
            structured["volume"] = _txt(_find(ec, "volume", ns))
            structured["issue"] = _txt(_find(ec, "issue", ns))
            structured["fpage"] = _txt(_find(ec, "fpage", ns))
            structured["lpage"] = _txt(_find(ec, "lpage", ns))
            structured["page_range"] = _txt(_find(ec, "page-range", ns))

            # persistentes
            doi_pub = _find(ec, "pub-id[@pub-id-type='doi']", ns)
            structured["doi"] = (doi_pub.text or "").strip() if doi_pub is not None and doi_pub.text else None
            ext_any = _find(ec, "ext-link", ns)
            if ext_any is not None:
                href = ext_any.get("{http://www.w3.org/1999/xlink}href") or ext_any.get("xlink:href")
                structured["uri"] = href or _txt(ext_any)

        references.append(
            _prune(
                {
                    "id": ref.get("id"),
                    "mixed_citation": mixed,
                    "structured": structured or None,
                }
            )
        )

    if references:
        record["references"] = references

    if include_raw_xml:
        record["raw_xml"] = xml_bytes.decode("utf-8", errors="ignore")

    return _prune(record)


# ---------------------- NDJSON & BULK ----------------------

def walk_and_convert(input_dir: Path, output_ndjson: Path, include_raw_xml: bool = False) -> int:
    count = 0
    output_ndjson.parent.mkdir(parents=True, exist_ok=True)
    with output_ndjson.open("w", encoding="utf-8") as out:
        for xml_file in sorted(input_dir.rglob("*.xml")):
            try:
                rec = parse_article(xml_file, include_raw_xml=include_raw_xml)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
            except Exception as e:
                print(f"[WARN] {xml_file}: {e}")
    return count


def write_bulk(input_ndjson: Path, bulk_out: Path, index_name: str) -> int:
    n = 0
    bulk_out.parent.mkdir(parents=True, exist_ok=True)
    with input_ndjson.open("r", encoding="utf-8") as src, bulk_out.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            doc = json.loads(line)
            ids = (doc.get("ids") or {})
            _id = ids.get("publisher-id") or ids.get("other") or doc.get("doi") or doc.get("source_file")
            dst.write(json.dumps({"index": {"_index": index_name, "_id": _id}}, ensure_ascii=False) + "\n")
            dst.write(line.strip() + "\n")
            n += 1
    return n


# ---------------------- CLI ----------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Converte XMLs SciELO/JATS para NDJSON e (opcional) arquivo _bulk do Elasticsearch."
    )
    ap.add_argument("-i", "--input", type=Path, required=True, help="Diretório raiz contendo XMLs (busca recursiva).")
    ap.add_argument("--out", type=Path, required=True, help="Arquivo NDJSON de saída.")
    ap.add_argument("--include-raw-xml", action="store_true", help="Inclui o XML original em cada registro JSON.")
    ap.add_argument("--bulk", type=Path, help="Gera arquivo _bulk para Elasticsearch (ações de index).")
    ap.add_argument("--index-name", default="scielo", help="Nome do índice no Elasticsearch para o _bulk.")
    args = ap.parse_args()

    total = walk_and_convert(args.input, args.out, include_raw_xml=args.include_raw_xml)
    print(f"[OK] {total} XMLs convertidos → {args.out}")

    if args.bulk:
        n = write_bulk(args.out, args.bulk, args.index_name)
        print(f"[OK] Bulk gerado com {n} docs → {args.bulk}")


if __name__ == "__main__":
    main()
