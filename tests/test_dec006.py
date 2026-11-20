import copy
import json
import random
from fractions import Fraction
from pathlib import Path
import pytest
from scipy.optimize import linprog
from seos.main import run, run_browser
from seos.engineering_optimizer import verify_engineering_plan

BASE=json.loads(Path('data/engineering_synthetic.json').read_text())


def test_different_densities_bank_billing():
    result=run(BASE)
    assert result['status']=='OPTIMAL'
    assert result['objective_exact']=='160'
    assert result['currency_result'] is None and result['dataset_kind']=='synthetic'
    x=[[Fraction(v) for v in row] for row in result['matrix_exact']]
    assert verify_engineering_plan(x,BASE,BASE['allowed'])
    assert sum(x[i][0] for i in range(3)) != BASE['compacted_volumes_m3'][0]
    assert run_browser(BASE)==result


@pytest.mark.parametrize('factor',[0,0.5,2,10])
def test_distance_scales_cost(factor):
    data=copy.deepcopy(BASE)
    data['distance_km']=[[factor*v for v in r] for r in data['distance_km']]
    result=run(data)
    assert result['status']=='OPTIMAL' and result['objective']==160*factor


@pytest.mark.parametrize('seed',range(80))
def test_independent_natural_variable_highs(seed):
    rng=random.Random(6000+seed)
    data=copy.deepcopy(BASE)
    rho=[1000,2000,4000]
    witness=[[rng.randint(0,12) for j in range(3)] for i in range(3)]
    data['bank_volumes_m3']=[sum(r) for r in witness]
    data['bank_dry_density_kg_m3']=rho
    data['compacted_dry_density_kg_m3']=[1000]*3
    data['compacted_volumes_m3']=[sum(rho[i]*witness[i][j] for i in range(3))//1000 for j in range(3)]
    data['distance_km']=[[rng.randint(0,10) for _ in range(3)] for _ in range(3)]
    data['haul_rate_cny_per_m3_km']=[[rng.randint(0,10) for _ in range(3)] for _ in range(3)]
    data['allowed']=[[witness[i][j]>0 or rng.random()>0.4 for j in range(3)] for i in range(3)]
    result=run(data)
    assert result['status']=='OPTIMAL'
    # Independent reference solves natural-volume variables directly; no product
    # LP matrix, conversion, feasibility routine or basis enumeration reused.
    A=[[int(k//3==i) for k in range(9)] for i in range(3)]
    A += [[(rho[k//3]/1000 if k%3==j else 0) for k in range(9)] for j in range(3)]
    b=data['bank_volumes_m3']+data['compacted_volumes_m3']
    c=[data['distance_km'][i][j]*data['haul_rate_cny_per_m3_km'][i][j] for i in range(3) for j in range(3)]
    bounds=[(0,None if data['allowed'][i][j] else 0) for i in range(3) for j in range(3)]
    oracle=linprog(c,A_eq=A,b_eq=b,bounds=bounds,method='highs')
    assert oracle.success
    assert result['objective']==pytest.approx(oracle.fun,abs=1e-7,rel=1e-10)
    # Exact independent checks of all six physical constraints and cost.
    x=[Fraction(v) for row in result['matrix_exact'] for v in row]
    assert all(sum(Fraction(str(a))*v for a,v in zip(row,x))==value for row,value in zip(A,b))
    assert sum(Fraction(cost)*value for cost,value in zip(c,x))==Fraction(result['objective_exact'])
    assert all(x[k]==0 for k,bound in enumerate(bounds) if bound[1]==0)


@pytest.mark.parametrize('value',[1e308,10**400,1e-300,float('inf'),float('nan'),-1,True,'1000'])
def test_density_adversarial(value):
    data=copy.deepcopy(BASE);data['bank_dry_density_kg_m3'][0]=value
    result=run(data)
    assert result['status']=='INVALID_INPUT'
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('key',['density_source','distance_source','rate_source'])
def test_provenance_missing(key):
    data=copy.deepcopy(BASE);data[key]=None
    assert run(data)['status']=='MISSING_DATA'


@pytest.mark.parametrize('key',['compatible_material','zero_dry_mass_loss','closed_balance'])
def test_no_implicit_model_assumptions(key):
    data=copy.deepcopy(BASE);data['scenario_conditions'][key]=False
    assert run(data)['status']=='UNSUPPORTED_MODEL'


def test_real_source_string_does_not_approve_measurements():
    data=copy.deepcopy(BASE);data['dataset_kind']='real'
    assert run(data)['status']=='SOURCE_REVIEW_REQUIRED'
    assert run(data)['currency_result'] is None


@pytest.mark.parametrize('state',['loose','compacted','unknown'])
def test_only_approved_billing_state(state):
    data=copy.deepcopy(BASE);data['billing_volume_state']=state
    assert run(data)['status']=='INVALID_INPUT'


def test_mass_not_equal_volume_balance():
    data=copy.deepcopy(BASE);data['compacted_volumes_m3']=[10,20,30]
    assert run(data)['status']=='UNBALANCED'


def test_micro_mass_forbidden_and_no_discard():
    data=copy.deepcopy(BASE)
    data.update(bank_volumes_m3=[1e-12,0,0],compacted_volumes_m3=[1e-12,0,0],bank_dry_density_kg_m3=[1]*3,compacted_dry_density_kg_m3=[1]*3,allowed=[[False]*3 for _ in range(3)])
    assert run(data)['status']=='INFEASIBLE'
    data['bank_volumes_m3']=[0]*3
    assert run(data)['status']=='UNBALANCED'


def test_verifier_detects_each_constraint_and_disabled_flow():
    result=run(BASE);x=[[Fraction(v) for v in r] for r in result['matrix_exact']]
    for i in range(3):
        broken=copy.deepcopy(x);broken[i][i]+=Fraction(1,10**12)
        assert not verify_engineering_plan(broken,BASE,BASE['allowed'])
    allowed=copy.deepcopy(BASE['allowed']);allowed[0][0]=False
    assert not verify_engineering_plan(x,BASE,allowed)


def test_max_numeric_domain_intermediates():
    data=copy.deepcopy(BASE)
    for key in ['bank_volumes_m3','compacted_volumes_m3','bank_dry_density_kg_m3','compacted_dry_density_kg_m3']:
        data[key]=[1e12]*3
    for key in ['haul_rate_cny_per_m3_km','distance_km']:
        data[key]=[[1e12]*3 for _ in range(3)]
    result=run(data)
    assert result['status']=='OPTIMAL' and result['objective']==pytest.approx(3e36)
    json.dumps(result,allow_nan=False)


def test_generated_bridge_uses_shared_engineering_code():
    html=Path('report/index.html').read_text(encoding='utf8')
    for name in ['def optimize_engineering','def verify_engineering_plan','result = run_browser(data)']:
        assert name in html


@pytest.mark.parametrize('literal',['1e-999','-1e-999','1e999'])
def test_raw_json_underflow_and_overflow(literal,tmp_path):
    import subprocess,sys
    text=json.dumps(BASE).replace('1000,',literal+',',1)
    file=tmp_path/'raw.json';file.write_text(text,encoding='utf8')
    process=subprocess.run([sys.executable,'-B','-m','seos.main','--input',str(file)],capture_output=True,text=True)
    assert process.returncode==2 and not process.stderr
    assert json.loads(process.stdout)['status']=='INVALID_INPUT'


@pytest.mark.parametrize('data',[None,[],5,True,{'metadata':float('inf')}])
def test_direct_engineering_entry_controlled(data):
    from seos.engineering import prepare
    from seos.engineering_optimizer import optimize_engineering
    assert prepare(data)['status']=='INVALID_INPUT'
    assert optimize_engineering(data)['status']=='INVALID_INPUT'


@pytest.mark.parametrize('literal',['0.100000000000000000001','10.0000000000000000001'])
def test_raw_excess_precision_rejected(literal,tmp_path):
    import subprocess,sys
    text=json.dumps(BASE).replace('1000,',literal+',',1)
    file=tmp_path/'precision.json';file.write_text(text,encoding='utf8')
    process=subprocess.run([sys.executable,'-B','-m','seos.main','--input',str(file)],capture_output=True,text=True)
    result=json.loads(process.stdout)
    assert process.returncode==2 and not process.stderr
    assert result['status']=='INVALID_INPUT' and result['error_code']=='NUMERIC_PRECISION'


def test_precision_parser_and_form_semantics():
    from seos.main import parse_json_number
    from seos.validation import number,InputError
    for token in ['0.100000000000000000001','10.0000000000000000001']:
        for action in [parse_json_number,number]:
            with pytest.raises(InputError) as error:action(token)
            assert error.value.code=='NUMERIC_PRECISION'
    for token in ['0.1000','1.00e-1','1e-12','1000000000000.0']:
        assert parse_json_number(token)==float(token)
