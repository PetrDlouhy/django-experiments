from django.contrib.sessions.backends.signed_cookies import SessionStore as SignedCookiesStore
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.cache import never_cache
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from experiments.utils import participant
from experiments.models import Experiment
from experiments import conf

TRANSPARENT_1X1_PNG = \
("\x89\x50\x4e\x47\x0d\x0a\x1a\x0a\x00\x00\x00\x0d\x49\x48\x44\x52"
 "\x00\x00\x00\x01\x00\x00\x00\x01\x08\x03\x00\x00\x00\x28\xcb\x34"
 "\xbb\x00\x00\x00\x19\x74\x45\x58\x74\x53\x6f\x66\x74\x77\x61\x72"
 "\x65\x00\x41\x64\x6f\x62\x65\x20\x49\x6d\x61\x67\x65\x52\x65\x61"
 "\x64\x79\x71\xc9\x65\x3c\x00\x00\x00\x06\x50\x4c\x54\x45\x00\x00"
 "\x00\x00\x00\x00\xa5\x67\xb9\xcf\x00\x00\x00\x01\x74\x52\x4e\x53"
 "\x00\x40\xe6\xd8\x66\x00\x00\x00\x0c\x49\x44\x41\x54\x78\xda\x62"
 "\x60\x00\x08\x30\x00\x00\x02\x00\x01\x4f\x6d\x59\xe1\x00\x00\x00"
 "\x00\x49\x45\x4e\x44\xae\x42\x60\x82\x00")


_MISSING = object()


@never_cache
@require_POST
def confirm_human(request):
    """Mark the session as belonging to a human, without clobbering the session.

    See _save_only_confirm_human_changes for why the session handling is not
    left to the middleware.
    """
    if not conf.CONFIRM_HUMAN:
        return HttpResponse(status=204)

    session = getattr(request, 'session', None)
    before = dict(session.items()) if session is not None else {}

    experiment_user = participant(request)
    experiment_user.confirm_human()

    _save_only_confirm_human_changes(session, before)
    return HttpResponse(status=204)


def _save_only_confirm_human_changes(session, before):
    """Persist this request's session changes without dropping concurrent ones.

    confirm_human() replays the participant's enrollments and goals - a counter
    round trip each - between writing its session flag and the session being
    saved at the end of the request. That can take seconds, and the middleware
    then writes back the whole session dict as it looked when this request
    loaded it: a concurrent request that wrote to the same session in the
    meantime (an OAuth login storing its state, for example) is silently
    overwritten by this request's stale snapshot.

    Instead, re-read the stored session, write only the keys confirm_human
    changed, and keep the middleware from saving the stale snapshot.
    """
    if session is None or not session.session_key:
        # No stored session yet, so there is nothing to race with - let the
        # middleware create and save the session as it normally would.
        return
    if isinstance(session, SignedCookiesStore):
        # Cookie-backed sessions have no server-side store to race on;
        # persistence is the response cookie the middleware writes.
        return

    changed = {key: value for key, value in session.items() if before.get(key, _MISSING) != value}

    fresh = type(session)(session_key=session.session_key)
    if changed:
        for key, value in changed.items():
            fresh[key] = value
        fresh.save()

    # The middleware must not write this request's stale snapshot over the
    # merge above. With SESSION_SAVE_EVERY_REQUEST=True it saves even an
    # unmodified session, so the request's session object is also pointed at
    # the merged state - whatever the middleware does, it persists that.
    # (_session_cache is the only way to replace the contents without
    # marking the session dirty.)
    session._session_cache = dict(fresh.items())
    session.modified = False


@never_cache
def record_experiment_goal(request, goal_name, cache_buster=None):
    participant(request).goal(goal_name)
    return HttpResponse(TRANSPARENT_1X1_PNG, content_type="image/png")


def change_alternative(request, experiment_name, alternative_name):
    experiment = get_object_or_404(Experiment, name=experiment_name)
    if alternative_name not in experiment.alternatives.keys():
        return HttpResponseBadRequest()

    participant(request).set_alternative(experiment_name, alternative_name)
    return HttpResponse('OK')
