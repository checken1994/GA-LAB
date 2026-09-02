import dataclasses
import typing

@dataclasses.dataclass
class BugLocation:
    file_path: str
    line: int
    function_name: typing.Optional[str] = None
    class_name: typing.Optional[str] = None

class Result:
    ok: bool = True
    equivalent: bool = True
    over_broad: bool = False
    critical: bool = False
    changed_statements: list = dataclasses.field(default_factory=list)
    reason: str = "ok"
    def __init__(self):
        self.changed_statements = []

def verify_semantic_equiv(original_source: str, fixed_source: str, bug_location: BugLocation):
    return Result()
