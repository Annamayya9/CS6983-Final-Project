"""Study UI for the production block-preserving tailoring engine."""
from resume_relevance import build_comparison
from resume_claims import tailor_blocks

def study_html(original):
    """Keep the same task/page while adding the proposed preference and review controls."""
    preferences = '''<fieldset><legend>Resume preferences</legend>
<label><input id="pref-education" name="education_first" type="checkbox"> Keep Education before Experience</label>
<label><input id="pref-wording" name="preserve_wording" type="checkbox"> Preserve original bullet and continuation wording exactly</label>
</fieldset><p id="review-permission" role="status">The current version needs explicit approval in the shared text channel.</p>'''
    result = original.replace('<button id="tailor"', preferences + '<button id="tailor"')
    result = result.replace('job_id:jobId,job_description:jd});',
                            "job_id:jobId,job_description:jd,preferences:{education_first:$('#pref-education').checked,preserve_wording:$('#pref-wording').checked}});")
    result = result.replace("$('#job-id').addEventListener('input', invalidate);",
                            "$('#job-id').addEventListener('input', invalidate);\n$('#pref-education').addEventListener('change', invalidate);\n$('#pref-wording').addEventListener('change', invalidate);")
    result = result.replace('<span>relevance points</span>', '<span>presentation-index points</span>')
    result = result.replace('3. Compare and review</h2>', '3. Compare and review</h2><p><strong>Presentation index:</strong> ordering affects the score; unchanged coverage means unchanged qualifications. Review your constraints before optimizing the score.</p>')
    result = result.replace("text('#before-text',r.source_text);", "text('#method',(r.score_interpretation||'')+' '+r.method); text('#before-text',r.source_text);")
    control = '''<script>
document.querySelector('#use-tailored').disabled=true;
setInterval(async()=>{try{
 const response=await fetch('/api/review-status'); const state=await response.json();
 document.querySelector('#use-tailored').disabled=!state.approved;
 document.querySelector('#review-permission').textContent=state.approved
 ?'The current version was explicitly approved through the shared text channel.'
 :'Ask the user to approve the current version through the shared text channel before selecting the file or submitting.';
}catch(error){document.querySelector('#use-tailored').disabled=true;}},1000);
</script>'''
    return result.replace('</html>', control + '</html>')
