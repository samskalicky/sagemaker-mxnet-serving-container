# Copyright 2019-2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.
from __future__ import absolute_import

import logging
import os

import boto3
import pytest
from sagemaker import LocalSession, Session
from sagemaker.mxnet import MXNet

from utils import image_utils

logger = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)
logging.getLogger('botocore').setLevel(logging.INFO)
logging.getLogger('factory.py').setLevel(logging.INFO)
logging.getLogger('auth.py').setLevel(logging.INFO)
logging.getLogger('connectionpool.py').setLevel(logging.INFO)

DIR_PATH = os.path.dirname(os.path.realpath(__file__))

# These regions have some p2 and p3 instances, but not enough for automated testing
NO_P2_REGIONS = ['ca-central-1', 'eu-central-1', 'eu-west-2', 'us-west-1', 'eu-west-3',
                 'eu-north-1', 'sa-east-1', 'ap-east-1', 'me-south-1']
NO_P3_REGIONS = ['ap-southeast-1', 'ap-southeast-2', 'ap-south-1', 'ca-central-1',
                 'eu-central-1', 'eu-west-2', 'us-west-1', 'eu-west-3', 'eu-north-1',
                 'sa-east-1', 'ap-east-1', 'me-south-1']


def pytest_addoption(parser):
    parser.addoption('--build-image', '-B', action='store_true')
    parser.addoption('--push-image', '-P', action='store_true')
    parser.addoption('--dockerfile-type', '-T',
                     choices=['dlc.cpu', 'dlc.gpu', 'mxnet.cpu', 'dlc.eia'],
                     default='mxnet.cpu')
    parser.addoption('--dockerfile', '-D', default=None)
    parser.addoption('--docker-base-name', default='sagemaker-mxnet-inference')
    parser.addoption('--region', default='us-west-2')
    parser.addoption('--framework-version', default=MXNet.LATEST_VERSION)
    parser.addoption('--py-version', default='3', choices=['2', '3', '2,3'])
    parser.addoption('--processor', default='cpu', choices=['gpu', 'cpu', 'cpu,gpu'])
    parser.addoption('--aws-id', default=None)
    parser.addoption('--instance-type', default=None)
    parser.addoption('--accelerator-type', default=None)
    # If not specified, will default to {framework-version}-{processor}-py{py-version}
    parser.addoption('--tag', default=None)


@pytest.fixture(scope='session', name='dockerfile_type')
def fixture_dockerfile_type(request):
    return request.config.getoption('--dockerfile-type')


@pytest.fixture(scope='session', name='dockerfile')
def fixture_dockerfile(request, dockerfile_type):
    dockerfile = request.config.getoption('--dockerfile')
    return dockerfile if dockerfile else 'Dockerfile.{}'.format(dockerfile_type)


@pytest.fixture(scope='session', name='build_image', autouse=True)
def fixture_build_image(request, framework_version, dockerfile, image_uri, region):
    build_image = request.config.getoption('--build-image')
    if build_image:
        return image_utils.build_image(framework_version=framework_version,
                                       dockerfile=dockerfile,
                                       image_uri=image_uri,
                                       region=region,
                                       cwd=os.path.join(DIR_PATH, '..'))

    return image_uri


@pytest.fixture(scope='session', name='push_image', autouse=True)
def fixture_push_image(request, image_uri, region, aws_id):
    push_image = request.config.getoption('--push-image')
    if push_image:
        return image_utils.push_image(image_uri, region, aws_id)
    return None


def pytest_generate_tests(metafunc):
    if 'py_version' in metafunc.fixturenames:
        py_version_params = ['py' + v for v in metafunc.config.getoption('--py-version').split(',')]
        metafunc.parametrize('py_version', py_version_params, scope='session')

    if 'processor' in metafunc.fixturenames:
        processor_params = metafunc.config.getoption('--processor').split(',')
        metafunc.parametrize('processor', processor_params, scope='session')


@pytest.fixture(scope='session')
def docker_base_name(request):
    return request.config.getoption('--docker-base-name')


@pytest.fixture(scope='session')
def region(request):
    return request.config.getoption('--region')


@pytest.fixture(scope='session')
def framework_version(request):
    return request.config.getoption('--framework-version')


@pytest.fixture(scope='session')
def aws_id(request):
    return request.config.getoption('--aws-id')


@pytest.fixture(scope='session')
def tag(request, framework_version, processor, py_version):
    provided_tag = request.config.getoption('--tag')
    default_tag = '{}-{}-{}'.format(framework_version, processor, py_version)
    return provided_tag if provided_tag is not None else default_tag


@pytest.fixture(scope='session')
def instance_type(request, processor):
    provided_instance_type = request.config.getoption('--instance-type')
    default_instance_type = 'ml.c4.xlarge' if processor == 'cpu' else 'ml.p2.xlarge'
    return provided_instance_type if provided_instance_type is not None else default_instance_type


@pytest.fixture(scope='session')
def accelerator_type(request):
    return request.config.getoption('--accelerator-type')


@pytest.fixture(name='docker_registry', scope='session')
def fixture_docker_registry(aws_id, region):
    return '{}.dkr.ecr.{}.amazonaws.com'.format(aws_id, region) if aws_id else None


@pytest.fixture(name='image_uri', scope='session')
def fixture_image_uri(docker_registry, docker_base_name, tag):
    if docker_registry:
        return '{}/{}:{}'.format(docker_registry, docker_base_name, tag)
    return '{}:{}'.format(docker_base_name, tag)


@pytest.fixture(scope='session')
def sagemaker_session(region):
    return Session(boto_session=boto3.Session(region_name=region))


@pytest.fixture(scope='session')
def sagemaker_local_session(region):
    return LocalSession(boto_session=boto3.Session(region_name=region))


@pytest.fixture(scope='session')
def local_instance_type(processor):
    return 'local' if processor == 'cpu' else 'local_gpu'


@pytest.fixture(autouse=True)
def skip_gpu_instance_restricted_regions(region, instance_type):
    no_p2 = region in NO_P2_REGIONS and instance_type.startswith('ml.p2')
    no_p3 = region in NO_P3_REGIONS and instance_type.startswith('ml.p3')
    if no_p2 or no_p3:
        pytest.skip('Skipping GPU test in region {} to avoid insufficient capacity'.format(region))
