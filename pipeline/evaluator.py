"""Primary evaluator: strict by default and deliberately non-repairing."""
import re
from pipeline.programs import execute_custom, primary_answers_equal

def normalize_surface(program):
    """Only non-semantic surface normalization permitted in primary metrics."""
    if not isinstance(program, str): return program
    text=program.strip()
    # EOF/marker casing is presentation-only; punctuation and program structure stay untouched.
    return re.sub(r"\s*(?:<eof>|eof)\s*$", "", text, flags=re.I).strip()

def evaluate_strict(predicted_program, gold_answer, table):
    try:
        program=normalize_surface(predicted_program)
        answer=execute_custom(program,table)
        return {"valid_program":True,"execution_accuracy":primary_answers_equal(answer,gold_answer),"answer":answer,"normalized_program":program}
    except Exception as exc:
        return {"valid_program":False,"execution_accuracy":False,"error":type(exc).__name__,"normalized_program":normalize_surface(predicted_program)}
