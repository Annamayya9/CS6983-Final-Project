"""Responses for the experiment's simulated human."""
def answer_question(case, question):
    question = question.lower()
    selector_request = any(term in question for term in ('selector', 'html structure', 'locate the fields', 'fields could not be located'))
    if not selector_request and case == 'T1' and ('sponsor' in question or 'work authorization' in question):
        return 'No.'
    if not selector_request and case == 'T2' and any(term in question for term in ('duration', 'how long', 'length of', 'number of months', 'number of years')):
        return 'Six months.'
    if not selector_request and case == 'T4' and any(term in question for term in ('consent', 'agree', 'approv', 'permission')):
        return 'I approve accepting this simulated consent.'
    return 'I do not have additional information.'
