## install docker

[docker for mac](https://store.docker.com/editions/community/docker-ce-desktop-mac)


## install docker-compose

docker-compose is included in docker for mac. on other platforms it may have to be installed separately.

## slim dump

you're gonna want to get yourself a [slim dump](https://github.com/Connexions/devops/wiki/How-To:-Get-a-Slim-Database-Dump)
follow the instructions for adding a volume on the `cnxdb` container for the sql file.

you may have to `docker-compose rm cnxdb && docker volume rm docker volume rm cnx-publishing_pgdata` if you've already created a container.

## create db manually

this will create a db and the app will turn on, but it will be empty, and thats not great for
development. you're probably better off doing the slim dump thing.

make celery make its tables

```bash
docker-compose exec worker /bin/bash -c "pshell development.ini"
```

```python
app.registry.celery_app.backend.ResultSession()
```

## turn it on
```bash
# foreground
docker-compose up
# background
docker-compose up -d
```
