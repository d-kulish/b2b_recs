#!/usr/bin/env python3
"""
Test Multitask Trainer Code Generation

Quick test to validate that TrainerModuleGenerator produces valid Python
code for multitask models.

Usage:
    python scripts/test_multitask_generation.py
"""

import os
import sys

# Setup Django
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from ml_platform.models import FeatureConfig, ModelConfig
from ml_platform.configs.services import TrainerModuleGenerator, validate_python_code


def test_multitask_generation():
    """Test that multitask trainer code can be generated and is valid Python."""

    print("=" * 70)
    print("TESTING MULTITASK TRAINER CODE GENERATION")
    print("=" * 70)

    # Find a ranking FeatureConfig (has target_column)
    ranking_fc = FeatureConfig.objects.filter(config_type='ranking').first()
    if not ranking_fc:
        print("ERROR: No ranking FeatureConfig found in database")
        print("Multitask requires a FeatureConfig with target_column set")
        return False

    print(f"\nUsing FeatureConfig: {ranking_fc.name} (ID: {ranking_fc.id})")
    print(f"  - config_type: {ranking_fc.config_type}")
    print(f"  - target_column: {ranking_fc.get_target_column_name()}")

    # Find or create a multitask ModelConfig
    multitask_mc = ModelConfig.objects.filter(model_type='multitask').first()

    if not multitask_mc:
        print("\nNo multitask ModelConfig found, looking for ranking ModelConfig...")
        ranking_mc = ModelConfig.objects.filter(model_type='ranking').first()

        if ranking_mc:
            print(f"Found ranking ModelConfig: {ranking_mc.name}")
            print("Creating temporary multitask config for testing...")

            # Create a temporary multitask config (don't save)
            multitask_mc = ModelConfig(
                name='Test Multitask Config',
                model_type='multitask',
                buyer_tower_layers=ranking_mc.buyer_tower_layers,
                product_tower_layers=ranking_mc.product_tower_layers,
                rating_head_layers=ranking_mc.rating_head_layers,
                output_embedding_dim=ranking_mc.output_embedding_dim,
                optimizer=ranking_mc.optimizer,
                learning_rate=ranking_mc.learning_rate,
                batch_size=ranking_mc.batch_size,
                epochs=2,
                retrieval_weight=1.0,
                ranking_weight=1.0,
                retrieval_algorithm='brute_force',
                top_k=100,
                loss_function=ranking_mc.loss_function,
            )
            # Don't save - just use for generation
        else:
            print("ERROR: No ranking ModelConfig found to base multitask on")
            return False
    else:
        print(f"\nUsing existing MultitaskConfig: {multitask_mc.name} (ID: {multitask_mc.id})")

    print(f"\nModelConfig details:")
    print(f"  - model_type: {multitask_mc.model_type}")
    print(f"  - retrieval_weight: {multitask_mc.retrieval_weight}")
    print(f"  - ranking_weight: {multitask_mc.ranking_weight}")
    print(f"  - output_embedding_dim: {multitask_mc.output_embedding_dim}")
    print(f"  - loss_function: {multitask_mc.loss_function}")

    # Generate trainer code
    print("\n" + "=" * 70)
    print("GENERATING MULTITASK TRAINER CODE")
    print("=" * 70)

    try:
        generator = TrainerModuleGenerator(ranking_fc, multitask_mc)
        code = generator.generate()

        print(f"\nGenerated code length: {len(code)} characters")
        print(f"Generated code lines: {len(code.splitlines())}")

        # Validate Python syntax
        print("\n" + "=" * 70)
        print("VALIDATING PYTHON SYNTAX")
        print("=" * 70)

        is_valid, error_msg, error_line = validate_python_code(code)

        if is_valid:
            print("\n[PASS] Generated code is valid Python!")
        else:
            print(f"\n[FAIL] Syntax error at line {error_line}: {error_msg}")

            # Show context around error
            lines = code.splitlines()
            start = max(0, error_line - 5)
            end = min(len(lines), error_line + 5)
            print("\nCode context:")
            for i in range(start, end):
                marker = ">>> " if i + 1 == error_line else "    "
                print(f"{marker}{i+1}: {lines[i]}")

            return False

        # Check for key components in generated code
        print("\n" + "=" * 70)
        print("CHECKING KEY COMPONENTS")
        print("=" * 70)

        checks = [
            ('MultitaskModel class', 'class MultitaskModel(tfrs.Model)'),
            ('retrieval_task', 'self.retrieval_task = tfrs.tasks.Retrieval()'),
            ('ranking_task', 'self.ranking_task = tfrs.tasks.Ranking('),
            ('RETRIEVAL_WEIGHT constant', 'RETRIEVAL_WEIGHT ='),
            ('RANKING_WEIGHT constant', 'RANKING_WEIGHT ='),
            ('compute_loss with weighted sum', 'self.retrieval_weight * retrieval_loss'),
            ('MultitaskServingModel', 'class MultitaskServingModel(tf.keras.Model)'),
            ('serve function (retrieval)', 'def serve(self, serialized_examples)'),
            ('serve_ranking function', 'def serve_ranking(self, serialized_examples)'),
            ('Dual signatures', "'serve_ranking': serving_model.serve_ranking"),
            ('rating_head tower tracking', "'rating_head'"),
        ]

        all_passed = True
        for name, pattern in checks:
            if pattern in code:
                print(f"  [PASS] {name}")
            else:
                print(f"  [FAIL] {name} - pattern not found: '{pattern}'")
                all_passed = False

        if all_passed:
            print("\n[SUCCESS] All component checks passed!")
        else:
            print("\n[WARNING] Some components are missing")

        # Save generated code for inspection
        output_path = '/tmp/generated_multitask_trainer.py'
        with open(output_path, 'w') as f:
            f.write(code)
        print(f"\nGenerated code saved to: {output_path}")

        # Print first 100 lines as sample
        print("\n" + "=" * 70)
        print("GENERATED CODE SAMPLE (first 100 lines)")
        print("=" * 70)
        lines = code.splitlines()
        for i, line in enumerate(lines[:100]):
            print(f"{i+1:4}: {line}")
        if len(lines) > 100:
            print(f"... ({len(lines) - 100} more lines)")

        return is_valid and all_passed

    except Exception as e:
        print(f"\n[ERROR] Failed to generate code: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_multitask_generation()
    sys.exit(0 if success else 1)
