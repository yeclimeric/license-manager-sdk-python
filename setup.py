from setuptools import setup, find_packages

setup(
    name="license-manager-sdk",
    version="1.0.0",
    packages=find_packages(include=['license_manager', 'license_manager.*']),
    install_requires=[
        'requests',
        'cryptography'
    ],
    python_requires='>=3.7',
)
