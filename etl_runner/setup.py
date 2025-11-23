"""
Setup script for ETL Runner Dataflow pipelines.

This packages the custom ETL code (dataflow_pipelines, extractors, loaders, utils)
so that Apache Beam can upload it to Dataflow worker VMs.
"""

from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open('requirements.txt') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='etl-runner-pipeline',
    version='1.0.0',
    description='B2B Recommendations ETL Runner - Dataflow Pipeline Package',
    author='B2B Recs Team',
    packages=find_packages(exclude=['tests', 'tests.*']),
    install_requires=requirements,
    python_requires='>=3.10',
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.10',
        'Operating System :: OS Independent',
    ],
)
