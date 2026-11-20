"""Validate pipeline steps and output links, then order their dependencies."""
from graphlib import CycleError, TopologicalSorter
import re

from isolation.files import fingerprint
from . import contracts, service
from .engine.inputs import pipeline_input_specs, validate_input_path
from .store import confined

MAX_STEPS = 16
STEP_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}")


def input_bindings(value):
    """Treat scalar inputs and file arrays as a sequence of bindings."""
    return value if isinstance(value, list) else [value]


def _validate_step(root, raw, isolated, fingerprints):
    fields = {"id", "pipeline", "inputs", "params", "cores", "timeout", "depends_on", "reason", "input_reasons"}
    if not isinstance(raw, dict) or raw.keys() - fields:
        raise ValueError("Each workflow step must use the declared workflow fields.")
    identifier, name = raw.get("id"), raw.get("pipeline")
    if not isinstance(identifier, str) or not STEP_NAME.fullmatch(identifier) or not isinstance(name, str):
        raise ValueError("Each step needs a valid id and pipeline name.")
    directory, manifest, config = (contracts.definition if isolated else service.definition)(name)
    inputs, params = raw.get("inputs", {}), raw.get("params", {})
    dependencies = raw.get("depends_on", [])
    if not isinstance(inputs, dict) or not isinstance(params, dict):
        raise ValueError(f"Step {identifier} needs input and parameter mappings.")
    reason, input_reasons = raw.get("reason", ""), raw.get("input_reasons", {})
    if not isinstance(reason, str) or len(reason) > 2000:
        raise ValueError(f"Step {identifier} needs a bounded textual reason.")
    if (not isinstance(input_reasons, dict) or input_reasons.keys() - inputs.keys()
            or any(not isinstance(value, str) or len(value) > 2000 for value in input_reasons.values())):
        raise ValueError(f"Step {identifier} has invalid input explanations.")
    if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
        raise ValueError(f"Step {identifier} needs a list of dependency step IDs.")
    dependencies = set(dependencies)
    cores = raw.get("cores", 1)
    max_cores, max_timeout = service.resource_bounds(manifest)
    if isolated and manifest["engine"] in contracts.LOCAL_ENGINES:
        from isolation.policy import WORKER_TIMEOUT
        max_timeout = min(max_timeout, WORKER_TIMEOUT)
    timeout = raw.get("timeout", max_timeout)
    if type(cores) is not int or type(timeout) is not int or not (1 <= cores <= max_cores and 1 <= timeout <= max_timeout):
        raise ValueError(f"Step {identifier} requires 1..{max_cores} cores and a timeout of 1..{max_timeout} seconds.")
    if isolated:
        contracts.validate_parameters(params, manifest, config)
    missing = service.required_parameters(manifest, params)
    if missing:
        names = ", ".join(item["name"] for item in missing)
        raise ValueError(f"Step {identifier} is missing required parameters: {names}.")
    _, outputs = service.plan_configuration(root, manifest, config, params)

    specs = pipeline_input_specs(manifest)
    missing_slots = {slot for slot, spec in specs.items() if spec["required"]} - inputs.keys()
    if missing_slots or inputs.keys() - specs.keys():
        raise ValueError(f"Step {identifier} has missing or invalid inputs. "
                         f"Missing: {sorted(missing_slots)}. Unknown: {sorted(inputs.keys() - specs.keys())}.")
    for slot, value in inputs.items():
        bindings = input_bindings(value)
        if not bindings or (len(bindings) > 1 and not specs[slot]["multiple"]):
            raise ValueError(f"Step {identifier} input {slot} has invalid file cardinality.")
        for binding in bindings:
            if isinstance(binding, str):
                path = confined(root, binding)
                if not path.is_file():
                    raise ValueError(f"Step {identifier} input {slot} requires an existing file: {binding}")
                validate_input_path(path, specs[slot])
                if binding not in fingerprints:
                    fingerprints[binding] = fingerprint(root, binding)
            elif (isinstance(binding, dict) and binding.keys() == {"step", "output"}
                  and all(isinstance(item, str) for item in binding.values())):
                dependencies.add(binding["step"])
            else:
                raise ValueError(f"Step {identifier} input {slot} needs a file path or a step/output reference.")
    explanations = {key: raw[key] for key in ("reason", "input_reasons") if key in raw}
    return {"id": identifier, "pipeline": name, "inputs": inputs, "params": params,
            "cores": cores, "timeout": timeout, "depends_on": sorted(dependencies), "status": "waiting",
            "definition_sha256": service.definition_hash(directory), "output_names": sorted(outputs), **explanations}


def build(root, steps, *, isolated, allow_single=False):
    """Return ordered, validated steps and fingerprints of their source files."""
    minimum = 1 if allow_single else 2
    if not isinstance(steps, list) or not minimum <= len(steps) <= MAX_STEPS:
        raise ValueError(f"A workflow must have between {minimum} and {MAX_STEPS} steps.")
    graph, fingerprints = {}, {}
    for raw in steps:
        step = _validate_step(root, raw, isolated, fingerprints)
        if step["id"] in graph:
            raise ValueError(f"Duplicate workflow step: {step['id']}.")
        graph[step["id"]] = step
    for step in graph.values():
        for dependency in step["depends_on"]:
            if dependency not in graph:
                raise ValueError(f"Step {step['id']} depends on unknown step {dependency}.")
        for value in step["inputs"].values():
            for binding in input_bindings(value):
                if isinstance(binding, dict) and binding["output"] not in graph[binding["step"]]["output_names"]:
                    raise ValueError(f"Step {binding['step']} does not declare output {binding['output']}.")
    try:
        order = TopologicalSorter({key: step["depends_on"] for key, step in graph.items()}).static_order()
        ordered = {key: graph[key] for key in order}
    except CycleError as exc:
        raise ValueError("Workflow dependencies contain a cycle.") from exc
    return ordered, fingerprints
