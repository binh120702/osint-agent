import os
import json
import sys
from jsonschema import validate, ValidationError

def validate_case_file(filepath, schema):
    print(f"Validating {os.path.basename(filepath)}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            case_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  [ERROR] Invalid JSON syntax: {e}")
            return False

    # 1. Structural Schema Validation
    try:
        validate(instance=case_data, schema=schema)
    except ValidationError as e:
        print(f"  [ERROR] Schema Validation Failed:")
        print(f"    Path: {list(e.path)}")
        print(f"    Message: {e.message}")
        return False

    # 2. Semantic Integrity Validation
    errors = []
    
    # Extract sets for quick lookup
    source_ids = {s['source_id'] for s in case_data.get('sources', [])}
    entity_ids = {e['id'] for e in case_data.get('ground_truth', {}).get('entities', [])}
    
    # A. Validate entities source references
    for entity in case_data.get('ground_truth', {}).get('entities', []):
        for ref in entity.get('source_references', []):
            if ref not in source_ids:
                errors.append(f"Entity '{entity['id']}' references undefined source_id '{ref}'")

    # B. Validate relations
    for rel in case_data.get('ground_truth', {}).get('relations', []):
        if rel['source'] not in entity_ids:
            errors.append(f"Relation source '{rel['source']}' is not a defined entity ID.")
        if rel['target'] not in entity_ids:
            errors.append(f"Relation target '{rel['target']}' is not a defined entity ID.")
        for ref in rel.get('source_references', []):
            if ref not in source_ids:
                errors.append(f"Relation from '{rel['source']}' to '{rel['target']}' references undefined source_id '{ref}'")

    # C. Validate contradictions
    for contra in case_data.get('ground_truth', {}).get('contradictions', []):
        for ref in contra.get('source_references', []):
            if ref not in source_ids:
                errors.append(f"Contradiction '{contra['contradiction_id']}' references undefined source_id '{ref}'")

    # D. Validate reasoning proof chains
    for step in case_data.get('ground_truth', {}).get('reasoning_proof_chains', []):
        for p_ent in step.get('premise_entities', []):
            if p_ent not in entity_ids:
                errors.append(f"Reasoning step {step['step_index']} references undefined premise entity '{p_ent}'")

    # E. Validate key findings
    for finding in case_data.get('ground_truth', {}).get('key_findings', []):
        for sup_ent in finding.get('supporting_entities', []):
            if sup_ent not in entity_ids:
                errors.append(f"Key finding '{finding['question'][:30]}...' references undefined supporting entity '{sup_ent}'")

    if errors:
        print(f"  [ERROR] Semantic integrity errors found:")
        for err in errors:
            print(f"    - {err}")
        return False

    print("  [SUCCESS] Case is fully valid.")
    return True

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    schema_path = os.path.join(project_dir, 'schema', 'case_schema.json')
    cases_dir = os.path.join(project_dir, 'cases')

    if not os.path.exists(schema_path):
        print(f"Schema file not found at {schema_path}")
        sys.exit(1)

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    if not os.path.exists(cases_dir):
        print(f"Cases directory not found at {cases_dir}")
        sys.exit(1)

    case_files = [os.path.join(cases_dir, f) for f in os.listdir(cases_dir) if f.endswith('.json')]
    if not case_files:
        print("No JSON case files found to validate.")
        sys.exit(0)

    all_valid = True
    for case_file in case_files:
        if not validate_case_file(case_file, schema):
            all_valid = False
            print("-" * 50)

    if all_valid:
        print("\nAll cases passed validation successfully.")
        sys.exit(0)
    else:
        print("\nSome cases failed validation. See details above.")
        sys.exit(1)

if __name__ == '__main__':
    main()
