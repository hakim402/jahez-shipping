"""No tools/mutations in provider output. Extra keys, coercion and invented cites fail closed."""
import re
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Short = Annotated[str, Field(max_length=200)]
Text = Annotated[str, Field(max_length=2000)]
Cites = Annotated[list[Annotated[str, Field(max_length=40)]], Field(min_length=1, max_length=8)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ProposedField(Strict):
    field: Literal['internal_order', 'bill_number', 'origin_en', 'origin_ar', 'destination_en', 'destination_ar']
    value: Short
    source_ids: Cites
    source_snippet: Annotated[str, Field(max_length=500)]


class Identifier(Strict):
    kind: Literal['invoice', 'bill', 'container', 'carrier', 'unknown']
    value: Annotated[str, Field(max_length=100)]
    source_ids: Cites
    source_snippet: Annotated[str, Field(max_length=500)]


class ProposedItem(Strict):
    description_source: Short
    description_en: Short
    description_ar: Short
    quantity: Annotated[str, Field(max_length=16)]
    unit: Annotated[str, Field(max_length=32)]
    unit_ar: Annotated[str, Field(max_length=32)]
    source_ids: Cites
    source_snippet: Annotated[str, Field(max_length=500)]


class Extraction(Strict):
    fields: Annotated[list[ProposedField], Field(max_length=6)]
    identifiers: Annotated[list[Identifier], Field(max_length=20)]
    items: Annotated[list[ProposedItem], Field(max_length=25)]
    missing_or_uncertain: Annotated[list[Short], Field(max_length=20)]
    warnings: Annotated[list[Short], Field(max_length=20)]


class Statement(Strict):
    english: Text
    arabic: Text
    source_ids: Cites


class Writing(Strict):
    statements: Annotated[list[Statement], Field(min_length=1, max_length=12)]
    warnings: Annotated[list[Short], Field(max_length=20)]


SCHEMAS = {'extraction': Extraction, 'summary': Writing, 'message': Writing, 'operational': Writing}
NUMBERS = re.compile(r'(?<!\w)\d+(?:[.,:/-]\d+)*(?!\w)')


def validate_output(kind, output, source):
    result = SCHEMAS[kind].model_validate(output).model_dump()
    sources = {s['id']: s for s in source['records']}
    candidates = (result['fields'] + result['identifiers'] + result['items']) if kind == 'extraction' else result['statements']
    for candidate in candidates:
        if any(c not in sources for c in candidate['source_ids']):
            raise ValueError('invalid_source')
        if 'source_snippet' in candidate:
            snippet = candidate['source_snippet'].strip()
            # Scan snippets are explicitly visually transcribed proposals; staff verifies page image.
            digital = [sources[c].get('text', '') for c in candidate['source_ids'] if not sources[c].get('scanned')]
            if not snippet or (len(digital) == len(candidate['source_ids']) and not any(snippet in t for t in digital)):
                raise ValueError('invalid_snippet')
    if kind == 'extraction':
        names = [v['field'] for v in result['fields']]
        if len(names) != len(set(names)):
            raise ValueError('duplicate_field')
        for field in result['fields']:
            limit = 100 if field['field'] in ('internal_order', 'bill_number') else 120
            if not field['value'].strip() or len(field['value']) > limit:
                raise ValueError('invalid_field')
        for item in result['items']:
            qty = Decimal(item['quantity'])
            if not qty.is_finite() or qty <= 0 or qty > Decimal('999999999.999') or qty.as_tuple().exponent < -3:
                raise ValueError('invalid_quantity')
            if not all(item[k].strip() for k in ('description_en', 'description_source', 'unit')):
                raise ValueError('invalid_item')
    else:
        # Reject new numeric quantities/dates/identifiers. This does not establish factual correctness.
        for statement in result['statements']:
            source_text = ' '.join(str(sources[c]) for c in statement['source_ids'])
            allowed = set(NUMBERS.findall(source_text))
            if set(NUMBERS.findall(statement['english'] + ' ' + statement['arabic'])) - allowed:
                raise ValueError('invented_number')
            if not statement['english'].strip() or not statement['arabic'].strip():
                raise ValueError('missing_translation')
    return result
