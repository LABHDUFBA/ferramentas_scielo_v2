#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SciELO JATS XML ➜ JSON (NDJSON) converter
-----------------------------------------
- Percorre pastas com XMLs do SciELO/JATS e gera NDJSON (1 JSON por linha)
- Extrai metadados (ids, títulos, autores com afiliações resolvidas no próprio autor),
  resumos, keywords (agrupadas por idioma), corpo do texto e referências (mistas e estruturadas)
- Opcional: inclui o XML bruto (--include-raw-xml)
- Opcional: gera arquivo _bulk do Elasticsearch (--bulk --index-name)
- Normalização: por padrão converte textos para minúsculas com exceções importantes
  (use --no-lowercase para desativar)

Uso:
    python scielo_xml_to_json.py \
        --input /caminho/XML \
        --out out.ndjson \
        [--include-raw-xml] \
        [--bulk out_bulk.ndjson --index-name scielo] \
        [--no-lowercase]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from lxml import etree


# ---------------------- helpers ----------------------


def _txt(el: Optional[etree._Element]) -> Optional[str]:
    """Texto do elemento (itertext) com espaços colapsados; None se vazio."""
    if el is None:
        return None
    text = " ".join(" ".join(el.itertext()).split()).strip()
    return text or None


def _find(
    root: Optional[etree._Element],
    path: str,
    ns: Optional[Dict[str, str]] = None,
) -> Optional[etree._Element]:
    return root.find(path, namespaces=ns) if root is not None else None


def _findall(
    root: Optional[etree._Element],
    path: str,
    ns: Optional[Dict[str, str]] = None,
) -> List[etree._Element]:
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


def _clean_text(el: etree._Element) -> str:
    return " ".join(" ".join(el.itertext()).split()).strip()


def _aff_to_flat(aff: Dict[str, Any]) -> str:
    """
    Constrói uma versão 'flat' e legível de uma afiliação.
    Ordem: org_name → department_1 → department_2 → city → state → country.
    """
    parts: List[str] = []
    for key in ("org_name", "department_1", "department_2", "city", "state", "country"):
        val = aff.get(key)
        if val:
            parts.append(str(val))
    # Remover duplicatas mantendo a ordem
    seen = set()
    ordered = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ", ".join(ordered)


def _extract_email_from_text(text: Optional[str]) -> Optional[str]:
    """
    Tenta encontrar um e-mail válido dentro de uma string usando regex.
    Retorna o primeiro encontrado ou None.
    """
    if not text:
        return None
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if match:
        return match.group(0)
    return None


# ---------------------- lowercase normalization ----------------------


def _lowercase_record(
    data: Any,
    *,
    skip_paths: Optional[Set[str]] = None,
    path: str = "",
) -> Any:
    """
    Converte strings para minúsculas recursivamente, exceto caminhos em skip_paths.
    - path usa notação "a.b[0].c".
    """
    if skip_paths is None:
        skip_paths = set()

    if path in skip_paths:
        return data

    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            child_path = f"{path}.{k}" if path else k
            out[k] = _lowercase_record(v, skip_paths=skip_paths, path=child_path)
        return out
    if isinstance(data, list):
        out_list = []
        for idx, v in enumerate(data):
            child_path = f"{path}[{idx}]"
            out_list.append(_lowercase_record(v, skip_paths=skip_paths, path=child_path))
        return out_list
    if isinstance(data, str):
        return data.lower()
    return data


# ---------------------- full text ----------------------


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
        paras = [_clean_text(p) for p in sec.findall(".//p")]
        paras = [p for p in paras if p]
        if title or paras:
            sections.append(_prune({"title": title, "paragraphs": paras}))

    # full_text concatenado
    all_paras = [_clean_text(p) for p in body.findall(".//p")]
    all_paras = [p for p in all_paras if p]
    full_text = "\n\n".join(all_paras) if all_paras else None
    return full_text, sections


# ---------------------- parsing principal ----------------------

def get_or_fallback(root, path, ns, fallback):
    el = _find(root, path, ns)
    return el if el is not None else fallback

def parse_xml_to_record(
    xml_path: Path,
    include_raw_xml: bool = False,
    lowercase: bool = True,
) -> Dict[str, Any]:
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    xml_bytes = xml_path.read_bytes()
    root = etree.fromstring(xml_bytes, parser=parser)
    ns = root.nsmap  # SciELO geralmente sem ns default; manter para compat.

    record: Dict[str, Any] = {"source_file": str(xml_path)}

    # article-type no <article>
    article_type = root.get("article-type")
    if article_type:
        record["article_type"] = article_type

    # front / article-meta
    front = get_or_fallback(root, "front", ns, root)
    article_meta = get_or_fallback(front, "article-meta", ns, front)

    # títulos e traduções
    title_group = _find(article_meta, "title-group", ns)
    if title_group is not None:
        record["article_title"] = _txt(_find(title_group, "article-title", ns))
        translations = []
        for alt in _findall(title_group, "trans-title-group", ns):
            translations.append(
                _prune(
                    {
                        "lang": alt.get("{http://www.w3.org/XML/1998/namespace}lang")
                        or alt.get("xml:lang"),
                        "title": _txt(_find(alt, "trans-title", ns))
                        or _txt(_find(alt, "article-title", ns)),
                    }
                )
            )
        if translations:
            record["article_title_translations"] = translations

    # ids
    article_ids = {}
    for aid in _findall(article_meta, "article-id", ns):
        id_type = aid.get("pub-id-type") or aid.get("pubid-type")
        val = (aid.text or "").strip()
        if id_type and val:
            article_ids[id_type] = val
    if article_ids:
        record["article_ids"] = article_ids

    # categorias (heading)
    cat_group = _find(article_meta, "article-categories/subj-group[@subj-group-type='heading']", ns)
    if cat_group is not None:
        record["article_category"] = _txt(_find(cat_group, "subject", ns))

    # journal meta
    journal_meta = _find(front, "journal-meta", ns)
    if journal_meta is not None:
        journal_id = _txt(_find(journal_meta, "journal-id", ns))
        journal_title = _txt(_find(journal_meta, "journal-title-group/journal-title", ns))
        if journal_id:
            record["journal_id"] = journal_id
        if journal_title:
            record["journal_title"] = journal_title

    # datas de publicação
    pub_dates: List[Dict[str, Any]] = []
    for pd in _findall(article_meta, "pub-date", ns):
        when = {
            "pub_type": pd.get("pub-type"),
            "year": _txt(_find(pd, "year", ns)),
            "month": _txt(_find(pd, "month", ns)),
            "day": _txt(_find(pd, "day", ns)),
            "season": _txt(_find(pd, "season", ns)),
        }
        when = _prune(when)
        if when:
            pub_dates.append(when)
    if pub_dates:
        record["pub_dates"] = pub_dates

    # páginas, volume, número
    record["volume"] = _txt(_find(article_meta, "volume", ns))
    record["issue"] = _txt(_find(article_meta, "issue", ns))
    record["fpage"] = _txt(_find(article_meta, "fpage", ns))
    record["lpage"] = _txt(_find(article_meta, "lpage", ns))

    # ---------------------- Afiliações + Notas + Autores ----------------------
    # 1) Mapear TODAS as <aff> dentro de article-meta (recursivo: .//aff)
    aff_map: Dict[str, Dict[str, Any]] = {}
    for aff in _findall(article_meta, ".//aff", ns):
        aff_id = aff.get("id")
        inst_original = _txt(_find(aff, "institution[@content-type='original']", ns))
        inst_normalized = _txt(_find(aff, "institution[@content-type='normalized']", ns))
        org_name = _txt(_find(aff, "institution[@content-type='orgname']", ns))
        department_1 = _txt(_find(aff, "institution[@content-type='orgdiv1']", ns))
        department_2 = _txt(_find(aff, "institution[@content-type='orgdiv2']", ns))
        city = _txt(_find(aff, "addr-line/named-content[@content-type='city']", ns))
        state = _txt(_find(aff, "addr-line/named-content[@content-type='state']", ns))
        country_el = _find(aff, "country", ns)
        country = _txt(country_el)
        country_code = country_el.get("country") if country_el is not None else None
        name_all = _txt(aff)

        aff_map[aff_id or f"aff_{len(aff_map)+1}"] = _prune(
            {
                "id": aff_id,
                "institution_original": inst_original,
                "institution_normalized": inst_normalized,
                "org_name": org_name or inst_normalized or inst_original or name_all,
                "department_1": department_1,
                "department_2": department_2,
                "city": city,
                "state": state,
                "country": country,
                "country_code": country_code,
                "name": name_all,
            }
        )

    # 2) Mapear notas de autor (<author-notes><fn id="...">)
    fn_map: Dict[str, Dict[str, Optional[str]]] = {}
    for fn in _findall(article_meta, ".//author-notes//fn", ns):
        fn_id = fn.get("id")
        if not fn_id:
            continue
        label = _txt(_find(fn, "label", ns))
        # pode haver vários <p> na nota
        ps = [_txt(p) for p in _findall(fn, "p", ns)]
        ps = [p for p in ps if p]
        text = " ".join(ps) if ps else _txt(fn)
        note_flat = " ".join([t for t in [label, text] if t])
        fn_map[fn_id] = {
            "id": fn_id,
            "label": label,
            "text": text,
            "note_flat": note_flat or None,
        }

    # 3) Autores
    contribs: List[Dict[str, Any]] = []
    for c in _findall(article_meta, "contrib-group/contrib", ns):
        if c.get("contrib-type") and c.get("contrib-type") != "author":
            continue

        given = _txt(_find(c, "name/given-names", ns))
        surname = _txt(_find(c, "name/surname", ns))
        email = _txt(_find(c, "email", ns))
        orcid_el = _find(c, "contrib-id[@contrib-id-type='orcid']", ns)
        orcid = (orcid_el.text or "").strip() if orcid_el is not None and orcid_el.text else None

        # roles (um autor pode ter vários <role>)
        roles = [_txt(r) for r in _findall(c, "role", ns)]
        roles = [r for r in roles if r]

        # 3a) coletar múltiplos IDs de afiliação a partir de <xref ref-type="aff" rid="...">
        raw_aff_ids: List[str] = []
        for xr in _findall(c, "xref[@ref-type='aff']", ns):
            rid = (xr.get("rid") or "").strip()
            if rid:
                raw_aff_ids.append(rid)
        aff_ids: List[str] = []
        for chunk in raw_aff_ids:
            for rid in [r for r in re.split(r"[\s,;]+", chunk) if r]:
                if rid not in aff_ids:
                    aff_ids.append(rid)

        # 3b) resolver afiliações por ID + pegar <aff> inline
        inline_affs: List[Dict[str, Any]] = []
        for aff in _findall(c, "aff", ns):
            inst_original = _txt(_find(aff, "institution[@content-type='original']", ns))
            inst_normalized = _txt(_find(aff, "institution[@content-type='normalized']", ns))
            org_name = _txt(_find(aff, "institution[@content-type='orgname']", ns)) or _txt(aff)
            department_1 = _txt(_find(aff, "institution[@content-type='orgdiv1']", ns))
            department_2 = _txt(_find(aff, "institution[@content-type='orgdiv2']", ns))
            city = _txt(_find(aff, "addr-line/named-content[@content-type='city']", ns))
            state = _txt(_find(aff, "addr-line/named-content[@content-type='state']", ns))
            country_el = _find(aff, "country", ns)
            country = _txt(country_el)
            country_code = country_el.get("country") if country_el is not None else None
            name_all = _txt(aff)
            inline_affs.append(
                _prune(
                    {
                        "id": None,
                        "institution_original": inst_original,
                        "institution_normalized": inst_normalized,
                        "org_name": org_name,
                        "department_1": department_1,
                        "department_2": department_2,
                        "city": city,
                        "state": state,
                        "country": country,
                        "country_code": country_code,
                        "name": name_all,
                    }
                )
            )

        aff_objs = [aff_map.get(aid) for aid in aff_ids if aff_map.get(aid)]
        if inline_affs:
            aff_objs.extend(inline_affs)
        aff_objs = aff_objs or None

        # 3c) coletar notas de autor por <xref ref-type="fn" rid="..."> e resolver em fn_map
        raw_fn_ids: List[str] = []
        for xr in _findall(c, "xref[@ref-type='fn']", ns):
            rid = (xr.get("rid") or "").strip()
            if rid:
                raw_fn_ids.append(rid)
        fn_ids: List[str] = []
        for chunk in raw_fn_ids:
            for rid in [r for r in re.split(r"[\s,;]+", chunk) if r]:
                if rid not in fn_ids:
                    fn_ids.append(rid)

        nota_author_list: List[Dict[str, Optional[str]]] = []
        for rid in fn_ids:
            note = fn_map.get(rid)
            if note:
                nota_author_list.append(note)

        nota_author = nota_author_list or None

        # tentar extrair e-mail das notas, se houver
        email_from_note = None
        if nota_author:
            for note in nota_author:
                candidate = _extract_email_from_text(note.get("text"))
                if candidate:
                    email_from_note = candidate
                    break

        # priorizar o email explícito do <email>, mas se não houver, usar o da nota
        final_email = email or email_from_note

        # 3d) flatten
        affiliation_flat = None
        if aff_objs:
            flat_list = [_aff_to_flat(a) for a in aff_objs if a]
            flat_list = [s for s in flat_list if s]
            affiliation_flat = flat_list or None

        full_name = " ".join([n for n in [given, surname] if n]).strip() or None
        parts_author_flat: List[str] = []
        if full_name:
            parts_author_flat.append(full_name)
        if orcid:
            parts_author_flat.append(f"ORCID: {orcid}")
        if final_email:
            parts_author_flat.append(f"Email: {final_email}")
        if affiliation_flat:
            parts_author_flat.append("Afiliações: " + " | ".join(affiliation_flat))
        # adicionar notas no author_flat
        if nota_author:
            notes_flat = [n.get("note_flat") for n in nota_author if n.get("note_flat")]
            if notes_flat:
                parts_author_flat.append("Notas: " + " | ".join(notes_flat))
        author_flat = " — ".join(parts_author_flat) if parts_author_flat else None

        contribs.append(
            _prune(
                {
                    "given": given,
                    "surname": surname,
                    "email": final_email or None,
                    "email_from_note": email_from_note or None,
                    "orcid": orcid or None,
                    "roles": roles or None,
                    "affiliations": aff_objs,
                    "affiliation_flat": affiliation_flat,
                    "nota_author": nota_author,  # lista de notas (id/label/text/note_flat)
                    "author_flat": author_flat,
                }
            )
        )

    if contribs:
        record["authors"] = contribs

    # resumos
    abstracts: List[Dict[str, Any]] = []
    for ab in _findall(article_meta, "abstract", ns):
        # evitar capturar graphic/table-wrap como "abstract"
        if ab.tag.endswith("abstract"):
            abstracts.append(
                _prune(
                    {
                        "lang": ab.get("{http://www.w3.org/XML/1998/namespace}lang")
                        or ab.get("xml:lang"),
                        "text": _txt(ab),
                    }
                )
            )
    if abstracts:
        record["abstracts"] = abstracts

    # keywords (kwd-group) → [{lang: [kw1, kw2, ...]}, ...]
    kw_by_lang: "OrderedDict[str, List[str]]" = OrderedDict()
    for kg in _findall(article_meta, "kwd-group", ns):
        # detectar idioma declarado (ex.: pt, en, es, fr, pt-BR...)
        lang = kg.get("{http://www.w3.org/XML/1998/namespace}lang") or kg.get("xml:lang")
        lang = (lang or "und").strip().lower()
        # normalizar subtags regionais (pt-br → pt)
        if "-" in lang:
            lang = lang.split("-")[0]
        # coletar keywords (ignorar <title>)
        kws = [_txt(k) for k in _findall(kg, "kwd", ns)]
        kws = [k for k in kws if k]
        if not kws:
            continue
        if lang not in kw_by_lang:
            kw_by_lang[lang] = []
        kw_by_lang[lang].extend(kws)
    if kw_by_lang:
        record["keywords"] = [{lang: lst} for lang, lst in kw_by_lang.items()]

    # full text
    full_text, sections = extract_full_text(root)
    if full_text:
        record["full_text"] = full_text
    if sections:
        record["full_text_sections"] = sections

    # referências
    references: List[Dict[str, Any]] = []
    ref_list = _find(article_meta, "ref-list", ns)
    if ref_list is not None:
        for ref in _findall(ref_list, "ref", ns):
            rid = ref.get("id")
            mixed = _txt(_find(ref, "mixed-citation", ns)) or _txt(ref)

            structured: Dict[str, Any] = {}
            ec = _find(ref, "element-citation", ns)
            if ec is not None:
                structured["publication_type"] = ec.get("publication-type")

                # autores da referência
                pgroup = _find(ec, "person-group", ns)
                if pgroup is not None:
                    authors = []
                    for nm in _findall(pgroup, "name", ns):
                        authors.append(
                            _prune(
                                {
                                    "surname": _txt(_find(nm, "surname", ns)),
                                    "given_names": _txt(_find(nm, "given-names", ns)),
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
                structured["doi"] = (
                    (doi_pub.text or "").strip()
                    if doi_pub is not None and doi_pub.text
                    else None
                )
                ext_any = _find(ec, "ext-link", ns)
                if ext_any is not None:
                    href = (
                        ext_any.get("{http://www.w3.org/1999/xlink}href")
                        or ext_any.get("xlink:href")
                    )
                    structured["uri"] = href or _txt(ext_any)

            references.append(
                _prune(
                    {
                        "id": rid,
                        "mixed_citation": mixed,
                        "structured": structured or None,
                    }
                )
            )
    if references:
        record["references"] = references

    # incluir XML bruto
    if include_raw_xml:
        record["raw_xml"] = xml_bytes.decode("utf-8", errors="ignore")

    # ---------- NORMALIZAÇÃO PARA MINÚSCULAS (com exceções) ----------
    record = _prune(record)
    if lowercase:
        # Campos a preservar (não converter para minúsculas):
        # - source_file
        # - abstracts[].text
        # - full_text
        # - full_text_sections[].paragraphs[*]
        # - raw_xml
        # - authors[].email, authors[].email_from_note, authors[].orcid
        # - article_ids.*  (preservar todos os IDs, incluindo doi, publisher-id, scielo-v3, pmid, pmcid, other-id, etc.)
        # - references[].structured.(doi|pmid|pmcid|uri)
        # - authors[].affiliations[].country_code
        skip: Set[str] = set()

        # source_file
        skip.add("source_file")

        # abstracts[].text
        for i, _ in enumerate(record.get("abstracts", []) or []):
            skip.add(f"abstracts[{i}].text")

        # full_text
        if "full_text" in record:
            skip.add("full_text")

        # full_text_sections[].paragraphs[*]
        for i, sec in enumerate(record.get("full_text_sections", []) or []):
            if isinstance(sec, dict) and isinstance(sec.get("paragraphs"), list):
                for j, _p in enumerate(sec["paragraphs"]):
                    skip.add(f"full_text_sections[{i}].paragraphs[{j}]")

        # raw_xml
        if "raw_xml" in record:
            skip.add("raw_xml")

        # authors[].email / email_from_note / orcid
        for i, _a in enumerate(record.get("authors", []) or []):
            skip.add(f"authors[{i}].email")
            skip.add(f"authors[{i}].email_from_note")
            skip.add(f"authors[{i}].orcid")

        # article_ids.* (preservar todos)
        if isinstance(record.get("article_ids"), dict):
            for k in record["article_ids"].keys():
                skip.add(f"article_ids.{k}")

        # references[].structured.(doi|pmid|pmcid|uri)
        for i, _r in enumerate(record.get("references", []) or []):
            skip.add(f"references[{i}].structured.doi")
            skip.add(f"references[{i}].structured.pmid")
            skip.add(f"references[{i}].structured.pmcid")
            skip.add(f"references[{i}].structured.uri")

        # authors[].affiliations[].country_code
        for i, a in enumerate(record.get("authors", []) or []):
            affs = a.get("affiliations") or []
            if isinstance(affs, list):
                for j, _aff in enumerate(affs):
                    skip.add(f"authors[{i}].affiliations[{j}].country_code")

        record = _lowercase_record(record, skip_paths=skip)

    return record


# ---------------------- IO (walk & write) ----------------------


def walk_and_convert(
    input_dir: Path,
    out_path: Path,
    include_raw_xml: bool = False,
    lowercase: bool = True,
) -> int:
    """
    Percorre recursivamente input_dir buscando *.xml e escreve NDJSON em out_path.
    Retorna o número de XMLs processados.
    """
    input_dir = Path(input_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with out_path.open("w", encoding="utf-8") as fout:
        for xml in sorted(input_dir.rglob("*.xml")):
            try:
                rec = parse_xml_to_record(
                    xml,
                    include_raw_xml=include_raw_xml,
                    lowercase=lowercase,
                )
            except Exception as exc:  # noqa: BLE001
                err = {
                    "source_file": str(xml),
                    "error": f"{type(exc).__name__}: {exc}",
                }
                fout.write(json.dumps(err, ensure_ascii=False) + "\n")
                continue

            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total += 1

    return total


def write_bulk(ndjson_path: Path, bulk_out: Path, index_name: str) -> int:
    """
    Gera um arquivo _bulk (NDJSON) para Elasticsearch a partir do NDJSON de entrada.
    Cada linha do NDJSON vira duas linhas no _bulk: meta + doc.
    """
    ndjson_path = Path(ndjson_path)
    bulk_out = Path(bulk_out)
    bulk_out.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with ndjson_path.open("r", encoding="utf-8") as fin, bulk_out.open(
        "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            meta = {"index": {"_index": index_name}}
            fout.write(json.dumps(meta, ensure_ascii=False) + "\n")
            fout.write(line + "\n")
            n += 1
    return n


# ---------------------- CLI ----------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="SciELO JATS XML ➜ NDJSON")
    ap.add_argument("--input", type=Path, required=True, help="Diretório com subpastas de XMLs.")
    ap.add_argument("--out", type=Path, required=True, help="Arquivo NDJSON de saída.")
    ap.add_argument(
        "--include-raw-xml",
        action="store_true",
        help="Inclui o XML bruto em 'raw_xml'.",
    )
    ap.add_argument(
        "--bulk",
        type=Path,
        help="Gera arquivo _bulk para Elasticsearch (ações de index).",
    )
    ap.add_argument(
        "--index-name",
        default="scielo",
        help="Nome do índice no Elasticsearch para o _bulk.",
    )
    ap.add_argument(
        "--no-lowercase",
        action="store_true",
        help="Não normaliza textos para minúsculas (preserva case original em todo o JSON).",
    )
    args = ap.parse_args()

    total = walk_and_convert(
        args.input,
        args.out,
        include_raw_xml=args.include_raw_xml,
        lowercase=not args.no_lowercase,
    )
    print(f"[OK] {total} XMLs convertidos → {args.out}")

    if args.bulk:
        n = write_bulk(args.out, args.bulk, args.index_name)
        print(f"[OK] Bulk gerado com {n} docs → {args.bulk}")


if __name__ == "__main__":
    main()
