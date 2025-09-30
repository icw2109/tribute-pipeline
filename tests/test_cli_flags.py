import subprocess, sys, os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

SCRIPTS = {
    'scrape': 'src/cli/scrape.py',
    'extract': 'src/cli/extract_insights.py',
    'classify': 'src/cli/classify.py',
}

def run_help(name):
    script = os.path.join(ROOT, SCRIPTS[name])
    assert os.path.exists(script), f"Missing script {script}"
    proc = subprocess.run([sys.executable, script, '--help'], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_scrape_help_contains_flags():
    out = run_help('scrape')
    for flag in ['--userAgent','--perPageLinkCap','--maxHtmlBytes','--noContentDedupe','--robotsFallbackAllow']:
        assert flag in out, f"Expected {flag} in scrape help"


def test_extract_help_contains_flags():
    out = run_help('extract')
    for flag in ['--baselineNeutralLen','--sectionHeuristic','--minhashFuzzy','--statsOut']:
        assert flag in out, f"Expected {flag} in extract help"


def test_classify_help_contains_flags():
    out = run_help('classify')
    # Unified classify CLI no longer exposes legacy flags like --metrics/--eval/--examples
    for flag in ['--in','--out','--config','--enable-self-train','--enable-zero-shot']:
        assert flag in out, f"Expected {flag} in classify help"
