import pytest
import transaction
import random

from pyramid import testing
from old.models import Tag
import old.views.tags


@pytest.fixture
def app_config():
    settings = {'sqlalchemy.url': 'sqlite:///:memory:'}
    config = testing.setUp(settings=settings)
    config.include('.models')
    yield config
    testing.tearDown()


@pytest.fixture
def db_session(app_config):
    session = app_config.registry['db_sessionmaker']()
    engine = session.bind
    Base.metadata.create_all(engine)
    return session


@pytest.fixture
def dummy_request(db_session):
    # Because we're using DummyRequest here, we need to manually add the
    # db_session to the request. config.add_request_method doesn't work
    # on dummy requests. No hardship though!
    return testing.DummyRequest(db_session=db_session)


@pytest.fixture
def basic_models(db_session):
    with transaction.manager:
        for i in range(10):
            kitten = Kitten(
                file_extension='.jpeg', file_data='DEADBEEF{0}'.format(i),
                source_url='http://example.com/{0}'.format(i),
                credit='Kitten {0}'.format(i))
            db_session.add(kitten)
    return [k.id for k in db_session.query(Kitten.id).order_by(Kitten.id.asc())]


@pytest.fixture
def models_with_votes(basic_models, db_session):
    for n in range(50):
        kitten_ids = random.sample(basic_models, 2)
        with transaction.manager:
            kittens = db_session.query(Kitten).filter(Kitten.id.in_(kitten_ids)).all()
            kittens[0].views += 1
            kittens[1].views += 1
            kittens[0].votes += 1
    # since we don't explicitly return anything, the fixture value is None
    # but we can still require it for its side effects
    # since the default fixture scope is 'function', it will be executed
    # every time it is required


def test_worst_view(dummy_request, db_session, models_with_votes):
    actual = views.worst(dummy_request)['kittens']
    # This is not the best example of a test, actually; the view under test
    # is so simple that the only way to test it is just to reiterate the query here.
    # but it does demonstrate the use of the database fixtures
    expected = db_session.query(Kitten).order_by(Kitten.votes.desc()).all()
    assert actual == expected
    last = actual[0]
    for current in actual[1:]:
        assert last.votes >= current.votes
        last = current


def test_see_choices(dummy_request, db_session, basic_models):
    for kitten in db_session.query(Kitten):
        assert kitten.views == 0
    actual = views.see_choices(dummy_request)['kittens']
    actual_ids = [k.id for k in actual]
    for kitten in db_session.query(Kitten):
        if kitten.id in actual_ids:
            assert kitten.views == 1
        else:
            assert kitten.views == 0


def test_vote(dummy_request, db_session, basic_models):
    kitten_id = random.choice(basic_models)
    assert db_session.query(Kitten).get(kitten_id).votes == 0
    dummy_request.POST['kitten'] = kitten_id
    views.vote(dummy_request)
    assert db_session.query(Kitten).get(kitten_id).votes == 1


def test_kitten_photo(dummy_request, db_session, basic_models):
    kitten_id = random.choice(basic_models)
    kitten = db_session.query(Kitten).get(kitten_id)
    dummy_request.matchdict['kitten'] = kitten_id
    response = views.kitten_photo(dummy_request)
    assert response.body == kitten.file_data
    assert response.content_type == 'image/jpeg'
