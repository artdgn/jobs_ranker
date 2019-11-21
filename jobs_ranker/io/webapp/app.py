import flask
import requests
from flask_bootstrap import Bootstrap

from jobs_ranker.common import HEADERS
from jobs_ranker.io.webapp.task_sessions import TasksSessions
from jobs_ranker.tasks.configs import TasksConfigsDao
from jobs_ranker.utils.logger import logger

app = flask.Flask(__name__)
app.secret_key = b'secret'
bootstrap = Bootstrap(app)

tasks = TasksSessions()


@app.route('/')
def instructions():
    flask.flash(f'redirected to tasks-list')
    return flask.redirect(flask.url_for('tasks_list'))


@app.route('/tasks/')
def tasks_list():
    task_urls = [{'name': t,
                  'url': flask.url_for('task_description', task_name=t)}
                 for t in TasksConfigsDao.all_names()]
    return flask.render_template('tasks_list.html',
                                 task_urls=task_urls,
                                 new_task=flask.url_for('new_task'))


@app.errorhandler(404)
def not_found(message):
    return flask.render_template(
        'error.html',
        message=message,
        back_url=flask.url_for('instructions'),
        back_text='Go back to start..'), 404


@app.route('/<task_name>/')
def task_description(task_name):
    task = tasks[task_name]

    return flask.render_template(
        'task_page.html',
        task_name=task_name,
        back_url=flask.url_for('tasks_list'),
        scrape_url=flask.url_for('scrape_task', task_name=task_name),
        label_url=flask.url_for('label_task', task_name=task_name),
        reload_url=flask.url_for('reload_ranker', task_name=task_name),
        edit_url=flask.url_for('edit_task', task_name=task_name),
        config_data=str(task.get_config()))


@app.route('/<task_name>/edit', methods=['GET', 'POST'])
def edit_task(task_name):
    task = tasks[task_name]
    back_url = flask.url_for('task_description', task_name=task_name)
    if flask.request.method == 'GET':

        if task.recent_edit_attempt:
            flask.flash(f'continuing previous edit, '
                        f'press "reset" to discard')
            text_data = task.recent_edit_attempt
        else:
            text_data = str(task.get_config())

        return flask.render_template(
            'edit_task.html',
            back_url=back_url,
            text_data=text_data
        )
    else:  # post
        form = flask.request.form

        if form.get('reset'):
            task.recent_edit_attempt = None
            flask.flash(f'resetting and discarding changes')
            return flask.redirect(flask.url_for('edit_task', task_name=task_name))

        try:
            task.update_config(form.get('text'))
            flask.flash(f'Task edit succesful!')
            return flask.redirect(back_url)

        except ValueError as e:
            message = str(e)
            flask.flash(f'Task edit error: {message}')
            return flask.redirect(flask.url_for('edit_task', task_name=task_name))


@app.route('/tasks/new_task/', methods=['GET', 'POST'])
def new_task():
    back_url = flask.url_for('tasks_list')
    if flask.request.method == 'GET':
        return flask.render_template('new_task.html', back_url=back_url)
    else:
        form = flask.request.form
        name = form.get('name')
        try:
            TasksConfigsDao.new_task(name)
            return flask.redirect(flask.url_for('edit_task', task_name=name))
        except ValueError as e:
            flask.flash(str(e))
            return flask.redirect(flask.url_for('new_task'))


@app.route('/<task_name>/label/')
def label_task(task_name):
    task = tasks[task_name]
    task.load_ranker()
    back_url = flask.url_for('task_description', task_name=task_name)

    if task.ranker.busy:
        return flask.render_template(
            'waiting.html',
            message='Waiting for ranker to crunch all the data',
            seconds=5,
            back_url=back_url,
            back_text=f'.. or go back: {back_url}')
    else:
        url = task.get_url()

        if url is None:
            return flask.render_template(
                'error.html',
                message=(f'No more new unlabeled jobs for task "{task_name}", '
                         f'try dedup off, or scrape new jobs'),
                back_url=back_url,
                back_text=f'Back: {back_url}')
        else:
            # go label it
            return flask.redirect(flask.url_for(
                'label_url',
                task_name=task_name,
                url=url))


@app.route('/<task_name>/label/<path:url>/', methods=['GET', 'POST'])
def label_url(task_name, url):
    task = tasks[task_name]
    task.load_ranker()
    back_url = flask.url_for('task_description', task_name=task_name)

    if task.ranker.busy:
        return flask.render_template(
            'waiting.html',
            message='Waiting for ranker to crunch all the data',
            seconds=5,
            back_url=back_url,
            back_text=f'.. or go back: {back_url}')

    if task.ranker_outdated():
        reload_url = flask.url_for('reload_ranker', task_name=task_name)
        logger.info(f'ranker outdated for "{task_name}" (new data scraped)')
        flask.flash(flask.Markup(
            f'New data scraped, "Reload" to update: '
            f'<a href="{reload_url}" class="alert-link">{reload_url}</a>'))

    data = task.ranker.url_data(url).drop('url')

    if flask.request.method == 'GET':
        return flask.render_template(
            'job_page.html',
            job_url=url,
            url_data=data,
            skip_url=flask.url_for('skip_url', task_name=task_name, url=url),
            recalc_url=flask.url_for('recalc', task_name=task_name),
            back_url=back_url,
            iframe_url=flask.url_for('source_posting', url=url)
        )

    else:
        form = flask.request.form
        if form.get('no'):
            resp = task.ranker.labeler.neg_label
        elif form.get('yes'):
            resp = task.ranker.labeler.pos_label
        else:
            resp = form['label']

        if not task.ranker.labeler.is_valid_label(str(resp)):
            # bad input, render same page again
            flask.flash(f'not a valid input: "{resp}", please relabel (or skip)')
            return flask.redirect(flask.url_for(
                'label_url',
                task_name=task_name,
                url=url))
        else:
            task.add_label(url, resp)
            flask.flash(f'labeled "{resp}" for ({url})')

        # label next
        return flask.redirect(flask.url_for(
            'label_task',
            task_name=task_name))


@app.route('/<task_name>/label/skip/<path:url>/')
def skip_url(task_name, url):
    task = tasks[task_name]
    task.skip(url)
    logger.info(f'skip: {url} for "{task_name}"')
    flask.flash(f'skipped url {url} for "{task_name}"')
    return flask.redirect(flask.url_for('label_task', task_name=task_name))


@app.route('/<task_name>/label/recalc/')
def recalc(task_name):
    task = tasks[task_name]
    task.recalc()
    logger.info(f'recalculating: {task_name}')
    flask.flash(f're-calculating rankings for task "{task_name}"')
    return flask.redirect(flask.url_for('label_task', task_name=task_name))


@app.route('/<task_name>/reload/')
def reload_ranker(task_name):
    task = tasks[task_name]
    if task.crawling:
        logger.info(f'not reloading ranker data because '
                    f'scraping is in progress: {task_name}')
        flask.flash(f'Scraping in progress, not reloading data.')
    if task.ranker.busy:
        logger.info(f'not reloading ranker data because '
                    f'ranker is busy (reloading or recalculating): {task_name}')
        flask.flash(f'Ranker is busy, not reloading data.')
    else:
        task.reload_ranker()
        logger.info(f'reloading ranker: {task_name}')
        flask.flash(f're-loading data for task "{task_name}"')
    return flask.redirect(flask.url_for('task_description', task_name=task_name))


@app.route('/source_posting/<path:url>')
def source_posting(url):
    return requests.get(url, headers=HEADERS).text


@app.route('/<task_name>/scrape/')
def scrape_task(task_name):
    task = tasks[task_name]
    back_url = flask.url_for('reload_ranker', task_name=task_name)

    try:
        days_since_last = task.days_since_last_crawl()
    except FileNotFoundError as e:
        days_since_last = None
        flask.flash(f'no crawl data found for task (is this a new task?)')

    if task.crawling:
        n_jobs = task.jobs_in_latest_crawl() or 0
        return flask.render_template(
            'waiting.html',
            message=(f'Waiting for crawler to finish '
                     f'({n_jobs} jobs in current file)'),
            seconds=30,
            back_url=back_url,
            back_text=(f'Reload or back (will not cancel scrape, '
                       f'will reload only if finished): {back_url}'))

    start_url = flask.url_for('scrape_start', task_name=task_name)

    return flask.render_template(
        'confirm.html',
        message=(f'Are you sure you want to start scraping? ' +
                 (f'latest data is from {days_since_last} day ago'
                  if days_since_last is not None else '')),
        option_1_url=start_url,
        option_1_text=f'Start:',
        option_2_url=back_url,
        option_2_text=f'Back and reload data:',
    )


@app.route('/<task_name>/scrape/start')
def scrape_start(task_name):
    task = tasks[task_name]
    task.start_crawl()
    logger.info(f'started scraping for {task_name}')
    flask.flash(f'Started scraping for task "{task_name}"')
    return flask.redirect(flask.url_for('scrape_task', task_name=task_name))


def start_server(debug=False, port=None):
    app.run(host='0.0.0.0', debug=debug, port=port)


if __name__ == '__main__':
    start_server(debug=True, port=5001)