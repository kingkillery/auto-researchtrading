from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FLY_ENTRYPOINT = REPO_ROOT / "fly_entrypoint.py"
DOCKERFILE = REPO_ROOT / "Dockerfile"
MANIFEST_PATH = REPO_ROOT / "docs" / "fly-runtime-manifest.json"


class FlyDockerContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_runtime_file_references_are_classified(self) -> None:
        referenced_paths = self._root_relative_paths_from_fly_entrypoint()
        unknown_paths = referenced_paths - self.required_files - self.optional_files - self.required_root_scripts
        self.assertEqual(
            set(),
            unknown_paths,
            "Classify every new ROOT-relative file used by fly_entrypoint.py as required or optional, "
            "then update docs/fly-runtime-manifest.json and the Dockerfile if needed.",
        )

    def test_required_runtime_paths_are_copied_into_image(self) -> None:
        copied_paths, copied_directories, copies_root_python = self._dockerfile_copy_contract()
        missing = self.required_files - copied_paths
        self.assertEqual(
            set(),
            missing,
            "Dockerfile is missing required Fly runtime inputs. Add explicit COPY entries for any new required files.",
        )
        missing_directories = self.required_directories - copied_directories
        self.assertEqual(
            set(),
            missing_directories,
            "Dockerfile is missing required Fly runtime directories. Add explicit COPY entries for them.",
        )
        self.assertEqual(
            self.root_python_entrypoints,
            copies_root_python,
            "Dockerfile root Python entrypoint copy rule drifted from docs/fly-runtime-manifest.json.",
        )

    def test_declared_runtime_paths_exist(self) -> None:
        missing = {
            relative_path
            for relative_path in self.required_files | self.optional_files | self.required_directories | self.required_root_scripts
            if not (REPO_ROOT / relative_path).exists()
        }
        self.assertEqual(set(), missing, "Fly Docker contract references files that do not exist in the repo.")

    def test_managed_root_scripts_are_classified(self) -> None:
        referenced_scripts = self._root_relative_python_scripts_from_fly_entrypoint()
        unknown_scripts = referenced_scripts - self.required_root_scripts
        self.assertEqual(
            set(),
            unknown_scripts,
            "Classify every repo-local Python script launched by fly_entrypoint.py and extend the Docker contract "
            "if orchestration grows beyond repo-root *.py files.",
        )

    def test_root_script_copy_contract_is_present(self) -> None:
        _, _, copies_root_python = self._dockerfile_copy_contract()
        self.assertEqual(
            self.root_python_entrypoints,
            copies_root_python,
            "Dockerfile must copy repo-root Python entrypoints while fly_entrypoint.py launches them by path.",
        )

    @property
    def required_files(self) -> set[str]:
        return set(self.manifest["required_files"])

    @property
    def optional_files(self) -> set[str]:
        return set(self.manifest["optional_files"])

    @property
    def required_directories(self) -> set[str]:
        return set(self.manifest["required_directories"])

    @property
    def required_root_scripts(self) -> set[str]:
        return set(self.manifest["required_root_scripts"])

    @property
    def root_python_entrypoints(self) -> bool:
        return bool(self.manifest["root_python_entrypoints"])

    def _root_relative_paths_from_fly_entrypoint(self) -> set[str]:
        tree = ast.parse(FLY_ENTRYPOINT.read_text(encoding="utf-8"))
        relative_paths: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value = self._extract_root_relative_path(node.value)
                if value is not None:
                    relative_paths.add(value)
        return relative_paths

    def _root_relative_python_scripts_from_fly_entrypoint(self) -> set[str]:
        return {
            relative_path
            for relative_path in self._root_relative_paths_from_fly_entrypoint()
            if relative_path.endswith(".py")
        }

    def _extract_root_relative_path(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = self._path_parts(node)
            if parts:
                return "/".join(parts)
            return None

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and len(node.args) == 1
        ):
            return self._extract_root_relative_path(node.args[0])

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "expanduser"
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id == "Path"
            and len(node.func.value.args) == 1
        ):
            return self._extract_root_relative_path(node.func.value.args[0])

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            for arg in node.args:
                extracted = self._extract_root_relative_path(arg)
                if extracted is not None:
                    return extracted

        return None

    def _path_parts(self, node: ast.AST) -> list[str] | None:
        if isinstance(node, ast.Name) and node.id == "ROOT":
            return []

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left = self._path_parts(node.left)
            if left is None:
                return None
            if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
                return [*left, node.right.value]

        return None

    def _dockerfile_copy_contract(self) -> tuple[set[str], set[str], bool]:
        copied_paths: set[str] = set()
        copied_directories: set[str] = set()
        copies_root_python = False
        for raw_line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line.startswith("COPY "):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            source = parts[1]
            if source == "*.py":
                copies_root_python = True
            if source in self.required_files:
                copied_paths.add(source)
            if source in self.required_directories:
                copied_directories.add(source)
        return copied_paths, copied_directories, copies_root_python


if __name__ == "__main__":
    unittest.main()
