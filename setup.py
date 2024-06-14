from setuptools import setup

setup(
    name='gym_patches',
    version='0.0.1',
    license='MIT',
    description='Applying edx-platform customizations for The Gymnasium',
    entry_points={
        'lms.djangoapp': [
            'gym_patches = gym_patches.apps:PatchesConfig',
        ],
},
)