import json
import subprocess
import sys
from pathlib import Path
import pytest
from seos.modules.optimizer import solve, verify_plan
from seos.modules.earthwork_calculator import convert_state
from seos.main import run

DATA=json.loads(Path('data/earthwork_example.json').read_text())


def test_tiny_forbidden_routes():
    assert solve([1e-8,0,0],[1e-8,0,0],[[1]*3 for _ in range(3)],[[False]*3 for _ in range(3)])['status']=='INFEASIBLE'


def test_tiny_positive_demand_is_not_discarded():
    assert solve([0]*3,[0,0,5e-8],DATA['costs'])['status']=='UNBALANCED'


def test_minimum_supported_positive_supply():
    result=solve([1e-12,0,0],[1e-12,0,0],[[1]*3 for _ in range(3)])
    assert result['status']=='OPTIMAL' and result['matrix'][0][0]==1e-12


@pytest.mark.parametrize('value',[1e308,10**400,1e-300,float('nan'),float('inf')])
def test_unsupported_costs_controlled(value):
    result=solve(DATA['supply'],DATA['demand'],[[value]*3 for _ in range(3)])
    assert result['status']=='INVALID_INPUT'
    json.dumps(result,allow_nan=False)


def test_sixth_constraint_independent_verifier():
    assert not verify_plan([[1,0,0],[0,1,0],[0,0,1]],[1]*3,[1,1,2],[[True]*3 for _ in range(3)])


@pytest.mark.parametrize('value',[1e308,10**400,1e-100])
def test_density_software_range(value):
    assert convert_state(1,value,1)['status']=='INVALID_INPUT'


def test_positive_underflow_case_rejected():
    assert convert_state(1e-300,1e-100,1e-100)['status']=='INVALID_INPUT'


def test_metadata_and_mode_validation():
    assert run(dict(DATA,metadata=float('inf')))['status']=='INVALID_INPUT'
    assert run(dict(DATA,mode='engineerng'))['status']=='INVALID_INPUT'


@pytest.mark.parametrize('metadata', ['\ud800', {'\udfff':'key'}])
def test_invalid_unicode_metadata(metadata):
    assert run(dict(DATA,metadata=metadata))['status']=='INVALID_INPUT'


def test_unicode_cli(tmp_path):
    for metadata, expected in [('earthwork 😀',0),('\ud800',2)]:
        path=tmp_path/'unicode.json';path.write_text(json.dumps(dict(DATA,metadata=metadata)),encoding='utf8')
        process=subprocess.run([sys.executable,'-B','-m','seos.main','--input',str(path)],capture_output=True,text=True)
        assert process.returncode==expected and not process.stderr
        json.loads(process.stdout)


@pytest.mark.parametrize('literal',['1e309','NaN','Infinity','-'+('9'*401)])
def test_cli_metadata_no_traceback(tmp_path,literal):
    text=json.dumps(DATA)[:-1]+',"metadata":'+literal+'}'
    source=tmp_path/'input.json';source.write_text(text,encoding='utf8')
    result=subprocess.run([sys.executable,'-B','-m','seos.main','--input',str(source)],capture_output=True,text=True)
    assert result.returncode==2 and not result.stderr
    assert json.loads(result.stdout)['status']=='INVALID_INPUT'
