from django.conf.urls.defaults import url, patterns
from views import css_preprocessor


urlpatterns = patterns('',
    url(r'^(.+)$', css_preprocessor, name='css-preprocessor')
)
