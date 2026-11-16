"""Collect direct human probes after an actual human-mode study session."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.run / 'config.json').read_text())
    if config['mode'] != 'human':
        parser.error('Subjective metrics can only be collected from a person after a human-mode run.')
    if any((args.run / name).exists() for name in ('survey.json', 'interview_notes.md')):
        parser.error('Feedback already exists; preserve the original responses.')
    registry = json.loads((ROOT / 'evaluation/core_metrics.json').read_text())
    answers = {}
    for name, item in registry['subjective_human_only'].items():
        while True:
            raw = input(item['question'] + f" (1={item['anchors'][0]}, 7={item['anchors'][1]}): ")
            try:
                value = int(raw)
                if 1 <= value <= 7:
                    answers[name] = value
                    break
            except ValueError:
                pass
            print('Please enter an integer from 1 to 7; stop the recorder if the participant declines.')
    survey = {'schema_version': 'team-core-v1', 'respondent_type': 'human', 'run_id': config['run_id'],
              'timestamp': datetime.now(timezone.utc).isoformat(), 'answers': answers}
    (args.run / 'survey.json').write_text(json.dumps(survey, indent=2), encoding='utf-8')
    print('Enter interviewer notes or direct participant quotes, one line at a time. Enter END to finish.')
    lines = []
    while True:
        line = input()
        if line == 'END':
            break
        lines.append(line)
    (args.run / 'interview_notes.md').write_text('# Human interview notes\n\nRun: ' + config['run_id'] + '\n\n' + '\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
